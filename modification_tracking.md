# Edit Modification Tracking with Timestamps

## Current State

Today, Test-Genie has two levels of persistence for manual edits:

1. **Immediate save** -- `extension.saveThisFeature` in [extension.ts](bdd-ai/extension/src/extension.ts) writes the updated text directly to the `.feature` file via `fs.writeFileSync`, with no metadata captured.
2. **Folder-level snapshots** -- `extension.saveVersionFolder` copies the entire `bdd_tests/` directory to `Versions/version_YYYYMMDD_HHMMSS/`. This is coarse-grained (whole-suite, not per-file) and captures no diff or source information.

**Gap**: There is no per-file edit history, no change diffs, no source attribution (manual vs. AI-generated), and no way for a user to see "what changed and when" for a given feature file.

## Recommended Approach: JSON Edit History Log

A JSON-based edit log is the best fit because it:

- Aligns with the existing **local-first, file-based** philosophy (no database needed)
- Requires **zero new dependencies** (Node.js built-in `crypto` for hashing)
- Produces human-readable, versionable artifacts
- Can be extended later with a UI diff viewer

### Storage Layout

```
<workspace>/
  .edit_history/
    functional/
      user_management_api.feature.history.json
    non_functional/
      security_probes.feature.history.json
```

Each `.history.json` file mirrors the path of its `.feature` file under `bdd_tests/`.

### Edit Entry Schema

```json
{
  "filePath": "bdd_tests/functional/user_management_api.feature",
  "entries": [
    {
      "id": "a1b2c3d4",
      "timestamp": "2026-02-09T14:30:00.000Z",
      "source": "manual_edit",
      "contentHashBefore": "sha256:abc123...",
      "contentHashAfter": "sha256:def456...",
      "contentSnapshot": "Feature: User Management API\n@smoke\nScenario: ...",
      "linesAdded": 3,
      "linesRemoved": 1,
      "diffSummary": "@@ -12,4 +12,6 @@ Scenario: Create user...",
      "versionTag": null
    }
  ]
}
```

Fields:

- `id` -- short unique identifier (first 8 chars of UUID)
- `timestamp` -- ISO 8601
- `source` -- `"manual_edit"` | `"ai_generated"` | `"ai_refined"` | `"external_edit"` | `"version_snapshot"`
- `contentHashBefore` / `contentHashAfter` -- SHA-256 of file contents before and after
- `contentSnapshot` -- full file content **after** the edit (enables per-entry restore)
- `linesAdded` / `linesRemoved` -- simple line-count delta
- `diffSummary` -- compact unified-diff snippet (truncated to first 50 lines max)
- `versionTag` -- version folder name if this edit was part of a "Save Version" action, otherwise `null`

---

## Implementation Plan

### 1. New module: `src/editTracker.ts`

Create a new TypeScript module with the following API:

```typescript
export type EditSource = "manual_edit" | "ai_generated" | "ai_refined" | "external_edit" | "version_snapshot";

export interface EditEntry {
  id: string;
  timestamp: string;
  source: EditSource;
  contentHashBefore: string;
  contentHashAfter: string;
  contentSnapshot: string;
  linesAdded: number;
  linesRemoved: number;
  diffSummary: string;
  versionTag: string | null;
}

export class EditTracker {
  constructor(private workspacePath: string) {}

  /** Log an edit event. Skips if old and new content are identical (no-op detection). */
  logEdit(filePath: string, oldContent: string, newContent: string, source: EditSource, versionTag?: string): void;

  /** Get history for a specific file. Returns [] on missing or corrupted history. */
  getFileHistory(filePath: string): EditEntry[];

  /** Get history across all tracked files. */
  getAllHistory(): { filePath: string; entries: EditEntry[] }[];

  /** Snapshot all current bdd_tests/ file hashes BEFORE AI generation starts. */
  snapshotBeforeGeneration(): Map<string, { hash: string; content: string }>;

  /** Compare post-generation state against a pre-generation snapshot and log changes. */
  logGenerationChanges(preSnapshot: Map<string, { hash: string; content: string }>): void;
}
```

Key implementation details:

- **No-op detection**: Compare `oldContent === newContent` (or hash comparison). If identical, skip logging entirely. This prevents noise from "save without changes" actions.
- **Content hashing**: Use `crypto.createHash('sha256')` (built into Node.js, zero dependencies).
- **Diff computation**: Simple line-based diff -- split by `\n`, compare line arrays, count added/removed, generate a compact summary truncated to 50 lines max.
- **Content snapshot**: Store full `newContent` in each entry to enable per-entry restore. For typical `.feature` files (a few KB each), this is acceptable storage.
- **Corruption recovery**: Wrap `JSON.parse()` in try/catch. On corruption, back up the corrupted file as `.history.json.bak`, start a fresh history, and log a warning via `vscode.window.showWarningMessage`.
- **Retention policy**: On each write, prune entries older than the newest 50 (configurable). This caps per-file history growth.
- **Error isolation**: All history I/O is wrapped in its own try/catch. History failures never prevent the actual `.feature` file save from succeeding. On failure, show a non-blocking warning.

### 2. Modify save command in `extension.ts`

In the `extension.saveThisFeature` command handler (lines 45-55 of [extension.ts](bdd-ai/extension/src/extension.ts)):

```typescript
const saveFileCmd = vscode.commands.registerCommand(
  "extension.saveThisFeature",
  async (filePath: string, updatedText: string) => {
    try {
      // Capture old content before overwrite
      const oldContent = fs.existsSync(filePath)
        ? fs.readFileSync(filePath, "utf8")
        : "";

      fs.writeFileSync(filePath, updatedText, "utf8");
      vscode.window.showInformationMessage("Feature file saved.");

      // Log the edit (isolated -- never blocks the save)
      try {
        editTracker.logEdit(filePath, oldContent, updatedText, "manual_edit");
      } catch (historyErr: any) {
        console.warn("Edit history logging failed:", historyErr.message);
      }
    } catch (err: any) {
      vscode.window.showErrorMessage("Failed to save feature file: " + err.message);
    }
  }
);
```

Critical: The `editTracker.logEdit` call is inside its own try/catch **after** the successful `writeFileSync`. A history logging failure never prevents a save.

### 3. Track AI-generated edits with pre-generation snapshot

The Python backend (`bdd_generation.py` lines 152-159) **deletes all existing `.feature` files** before writing new ones. So we cannot compare "after" -- the old files are already gone by the time the TypeScript extension regains control.

**Solution**: Snapshot **before** calling `generateTests()`, then diff **after** it returns.

In the `extension.generateBDD` handler (lines 99-138 of [extension.ts](bdd-ai/extension/src/extension.ts)):

```typescript
const generateCmd = vscode.commands.registerCommand("extension.generateBDD", async () => {
  // ... existing guards ...

  // BEFORE generation: snapshot all current feature file contents
  const preSnapshot = editTracker.snapshotBeforeGeneration();

  vscode.window.withProgress({ ... }, async (progress, token) => {
    try {
      const result = await generateTests(workspacePath, token);

      // AFTER generation: diff against snapshot and log changes
      try {
        editTracker.logGenerationChanges(preSnapshot);
      } catch (historyErr: any) {
        console.warn("AI generation history logging failed:", historyErr.message);
      }

      // ... existing panel/notification logic ...
    } catch (err: any) { ... }
  });
});
```

`snapshotBeforeGeneration()` walks `bdd_tests/` and stores `{ filePath -> { hash, content } }`. `logGenerationChanges()` walks `bdd_tests/` again after generation, compares hashes, and logs entries for:

- **New files** (not in snapshot): `source: "ai_generated"`, oldContent = ""
- **Changed files** (hash mismatch): `source: "ai_generated"`, oldContent from snapshot
- **Deleted files** (in snapshot but gone): `source: "ai_generated"`, newContent = "" (file removed)

### 4. Track external edits via file system watcher

If a user edits a `.feature` file directly in VS Code's native editor (not through the BDD Panel), that edit currently bypasses tracking entirely.

**Solution**: Add a `workspace.onDidSaveTextDocument` listener in `activate()`:

```typescript
vscode.workspace.onDidSaveTextDocument((doc) => {
  if (!doc.fileName.endsWith(".feature")) return;
  if (!doc.fileName.includes("bdd_tests")) return;

  // Skip if this save was triggered by our own saveThisFeature command
  // (use a flag set/cleared around that command)
  if (isSavingFromPanel) return;

  try {
    // We don't have the old content here, so read the history
    // to get the last known contentSnapshot, or use "" as fallback
    const lastEntry = editTracker.getFileHistory(doc.fileName).slice(-1)[0];
    const oldContent = lastEntry?.contentSnapshot ?? "";
    editTracker.logEdit(doc.fileName, oldContent, doc.getText(), "external_edit");
  } catch (err: any) {
    console.warn("External edit tracking failed:", err.message);
  }
});
```

### 5. Add "History" button and panel UI in `panel.ts`

**Button placement** -- add to the existing button row ([panel.ts](bdd-ai/extension/src/panel.ts) line 258-267):

```html
<div class="right-buttons">
  <button id="viewHistory" disabled>History</button>
  <button id="saveFeature">Save</button>
  <button id="saveVersion">Save Version</button>
</div>
```

**Disable state**: The History button starts disabled. When `setFilePath(path)` is called with a non-null path, the extension sends a message to enable it. When `setFilePath(null)` (directory selected), it stays disabled.

**Message flow**:

1. User clicks "History" -> webview sends `{ type: "viewHistory" }`
2. Extension reads history JSON for `currentFilePath` via `editTracker.getFileHistory()`
3. Extension sends `{ type: "historyData", entries: [...] }` back to webview
4. Webview renders the history UI

### 6. History panel UI -- collapsible section below the editor

The history view renders **below the editor** as a collapsible section, not replacing the editor content. This preserves the user's editing context.

```html
<div id="historySection" style="display:none;">
  <h3>Edit History <button id="closeHistory">Close</button></h3>
  <div id="historyTimeline">
    <!-- Entries rendered here dynamically -->
  </div>
</div>
```

Each timeline entry shows:

- **Timestamp** in relative format ("2 hours ago") with full ISO on hover
- **Source badge**: color-coded pill -- blue for "AI Generated", green for "Manual Edit", gray for "External Edit", purple for "Version Snapshot"
- **Change summary**: "+3 lines, -1 line"
- **Diff toggle**: "Show diff" expands to show the `diffSummary`
- **Restore button**: "Restore this version" -- sends `{ type: "restore", entryId: "..." }` to the extension, which writes the `contentSnapshot` back to the file and updates the editor

**Empty state**: When no history exists for a file, show: "No edit history yet. History will be recorded when you save changes."

### 7. Restore from history entry

When user clicks "Restore" on a history entry:

1. Webview sends `{ type: "restore", entryId: "a1b2c3d4" }` to extension
2. Extension looks up the entry's `contentSnapshot` from the history JSON
3. Extension reads current file content as `oldContent`
4. Extension writes `contentSnapshot` to the file via `fs.writeFileSync`
5. Extension logs a new entry: `source: "manual_edit"` (the restore itself is a tracked edit)
6. Extension sends `{ type: "setFeatureText", text: contentSnapshot }` to update the webview editor
7. Show info message: "Restored to version from {timestamp}"

### 8. Show last-modified indicator in Feature Explorer

Enhance the tree item tooltip in `FeatureTreeDataProvider` (line 354 of [extension.ts](bdd-ai/extension/src/extension.ts)):

```typescript
// Current tooltip
item.tooltip = `${full}\n${isDir ? "Folder" : "Feature File"}...`;

// Enhanced tooltip -- append last edit info
if (!isDir) {
  try {
    const history = editTracker.getFileHistory(full);
    const last = history[history.length - 1];
    if (last) {
      item.tooltip += `\nLast edited: ${last.timestamp}`;
      item.tooltip += `\nSource: ${last.source}`;
    }
  } catch { /* ignore */ }
}
```

### 9. Link "Save Version" to edit history

When `saveVersionFolder` runs (lines 57-96 of [extension.ts](bdd-ai/extension/src/extension.ts)):

1. **After** the folder copy succeeds, iterate all `.feature` files in `bdd_tests/`
2. For each file, log a `source: "version_snapshot"` entry with `versionTag` set to the version folder name (e.g., `"version_20260209_143000"`)
3. Also copy `.edit_history/` into the version snapshot folder

This ties the two systems together so users can see in the history: "this state was captured in version_20260209_143000."

### 10. Add `.edit_history/` to `.gitignore`

Append `.edit_history/` to the workspace `.gitignore` if it exists (or create a note in the README). This is developer-local metadata by default. Teams who want shared audit trails can remove it from `.gitignore`.

---

## Edge Cases and Robustness

- **No-op saves**: Detected by content comparison. No history entry is logged if nothing changed. Prevents noise.
- **First-ever save of a new file**: `oldContent` is `""`. Entry is logged with `contentHashBefore` of empty string. This is the "creation" event.
- **AI generation wipes all files**: Handled by the pre-generation snapshot approach (step 3). Old content is captured before Python backend runs.
- **External edits outside BDD Panel**: Caught by `onDidSaveTextDocument` watcher (step 4). Old content is approximated from the last history entry's `contentSnapshot`.
- **Corrupted history JSON**: `JSON.parse` failure is caught, corrupted file backed up as `.bak`, fresh history started, one-time warning shown.
- **Disk full / permission errors**: All history I/O is in isolated try/catch blocks. History failure never blocks the actual file save.
- **History file growth**: Retention policy prunes to the newest 50 entries per file on each write.
- **File renamed/moved outside extension**: Orphaned history files remain but don't cause errors. Could add a periodic cleanup in a future enhancement.
- **Multiple rapid saves**: Each save that actually changes content gets its own entry with a distinct timestamp. No-op detection prevents duplicates if content hasn't changed.

---

## Scope and Phasing

**Phase 1 (Core -- must have)**:

- `editTracker.ts` module with all robustness features (no-op detection, corruption recovery, retention, error isolation)
- Save command integration (`manual_edit`)
- AI generation snapshot tracking (`ai_generated`)
- `.gitignore` entry

**Phase 2 (UI -- should have)**:

- History button (disabled when no file selected)
- Collapsible history timeline below editor
- Source badges and diff summaries
- Restore from history entry
- Feature Explorer last-modified tooltip

**Phase 3 (Enhancements -- nice to have)**:

- External edit watcher (`external_edit`)
- Version snapshot linking (`version_snapshot` entries + copy `.edit_history/` into snapshots)
- Filter history by source type
- Export history as CSV/report
- Side-by-side diff viewer

