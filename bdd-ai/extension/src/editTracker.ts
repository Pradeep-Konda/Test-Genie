import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import * as vscode from "vscode";

export type EditSource =
  | "manual_edit"
  | "ai_generated"
  | "ai_refined"
  | "external_edit"
  | "version_snapshot";

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

interface HistoryFile {
  filePath: string;
  entries: EditEntry[];
}

const MAX_ENTRIES_PER_FILE = 50;
const MAX_DIFF_LINES = 50;

export class EditTracker {
  private historyRoot: string;

  constructor(private workspacePath: string) {
    this.historyRoot = path.join(workspacePath, ".edit_history");
  }

  /* ============================
     Public API
     ============================ */

  logEdit(
    filePath: string,
    oldContent: string,
    newContent: string,
    source: EditSource,
    versionTag: string | null = null
  ): void {
    if (oldContent === newContent) return; // no-op detection

    const historyPath = this.getHistoryFilePath(filePath);
    this.ensureDir(path.dirname(historyPath));

    const history = this.readHistory(historyPath, filePath);

    const beforeHash = this.hash(oldContent);
    const afterHash = this.hash(newContent);

    const diff = this.computeDiff(oldContent, newContent);

    const entry: EditEntry = {
      id: crypto.randomUUID().slice(0, 8),
      timestamp: new Date().toISOString(),
      source,
      contentHashBefore: beforeHash,
      contentHashAfter: afterHash,
      contentSnapshot: newContent,
      linesAdded: diff.linesAdded,
      linesRemoved: diff.linesRemoved,
      diffSummary: diff.summary,
      versionTag,
    };

    history.entries.push(entry);

    // retention policy
    if (history.entries.length > MAX_ENTRIES_PER_FILE) {
      history.entries = history.entries.slice(-MAX_ENTRIES_PER_FILE);
    }

    this.writeHistory(historyPath, history);
  }

  getFileHistory(filePath: string): EditEntry[] {
    try {
      const historyPath = this.getHistoryFilePath(filePath);
      if (!fs.existsSync(historyPath)) return [];

      const raw = fs.readFileSync(historyPath, "utf8");
      const parsed = JSON.parse(raw) as HistoryFile;

      return Array.isArray(parsed.entries) ? parsed.entries : [];
    } catch {
      return [];
    }
  }

  getAllHistory(): { filePath: string; entries: EditEntry[] }[] {
    if (!fs.existsSync(this.historyRoot)) return [];

    const results: { filePath: string; entries: EditEntry[] }[] = [];

    const walk = (dir: string) => {
      for (const item of fs.readdirSync(dir)) {
        const full = path.join(dir, item);
        const stat = fs.statSync(full);

        if (stat.isDirectory()) {
          walk(full);
        } else if (item.endsWith(".history.json")) {
          try {
            const parsed = JSON.parse(fs.readFileSync(full, "utf8")) as HistoryFile;
            if (parsed?.filePath && Array.isArray(parsed.entries)) {
              results.push({ filePath: parsed.filePath, entries: parsed.entries });
            }
          } catch {
            /* ignore corrupted files */
          }
        }
      }
    };

    walk(this.historyRoot);
    return results;
  }

  snapshotBeforeGeneration(): Map<string, { hash: string; content: string }> {
    const snapshot = new Map<string, { hash: string; content: string }>();
    const bddRoot = path.join(this.workspacePath, "bdd_tests");

    if (!fs.existsSync(bddRoot)) return snapshot;

    this.walkFiles(bddRoot, (file) => {
      if (!file.endsWith(".feature")) return;

      const content = fs.readFileSync(file, "utf8");
      snapshot.set(file, {
        content,
        hash: this.hash(content),
      });
    });

    return snapshot;
  }

  logGenerationChanges(
    preSnapshot: Map<string, { hash: string; content: string }>
  ): void {
    const bddRoot = path.join(this.workspacePath, "bdd_tests");
    const seen = new Set<string>();

    // new + modified files
    if (fs.existsSync(bddRoot)) {
      this.walkFiles(bddRoot, (file) => {
        if (!file.endsWith(".feature")) return;

        const content = fs.readFileSync(file, "utf8");
        const hash = this.hash(content);
        const prev = preSnapshot.get(file);

        seen.add(file);

        if (!prev) {
          // new file
          this.logEdit(file, "", content, "ai_generated");
        } else if (prev.hash !== hash) {
          // modified
          this.logEdit(file, prev.content, content, "ai_generated");
        }
      });
    }

    // deleted files
    for (const [file, prev] of preSnapshot.entries()) {
      if (!seen.has(file)) {
        this.logEdit(file, prev.content, "", "ai_generated");
      }
    }
  }

  /* ============================
     Internal helpers
     ============================ */

  private getHistoryFilePath(featureFilePath: string): string {
    const relative = path.relative(
      path.join(this.workspacePath, "bdd_tests"),
      featureFilePath
    );

    return path.join(
      this.historyRoot,
      relative + ".history.json"
    );
  }

  private readHistory(historyPath: string, filePath: string): HistoryFile {
    if (!fs.existsSync(historyPath)) {
      return { filePath, entries: [] };
    }

    try {
      return JSON.parse(fs.readFileSync(historyPath, "utf8")) as HistoryFile;
    } catch (err) {
      // corruption recovery
      try {
        fs.renameSync(historyPath, historyPath + ".bak");
      } catch {
        /* ignore */
      }

      vscode.window.showWarningMessage(
        `Edit history for ${path.basename(filePath)} was corrupted and has been reset.`
      );

      return { filePath, entries: [] };
    }
  }

  private writeHistory(historyPath: string, history: HistoryFile): void {
    try {
      fs.writeFileSync(historyPath, JSON.stringify(history, null, 2), "utf8");
    } catch (err) {
      throw new Error("Failed to write edit history");
    }
  }

  private ensureDir(dir: string): void {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }

  private hash(content: string): string {
    return (
      "sha256:" +
      crypto.createHash("sha256").update(content, "utf8").digest("hex")
    );
  }

  private computeDiff(oldText: string, newText: string): {
    linesAdded: number;
    linesRemoved: number;
    summary: string;
  } {
    const oldLines = oldText.split("\n");
    const newLines = newText.split("\n");

    let added = 0;
    let removed = 0;

    const diffLines: string[] = [];
    const max = Math.max(oldLines.length, newLines.length);

    for (let i = 0; i < max; i++) {
      const o = oldLines[i];
      const n = newLines[i];

      if (o === undefined && n !== undefined) {
        added++;
        diffLines.push(`+ ${n}`);
      } else if (o !== undefined && n === undefined) {
        removed++;
        diffLines.push(`- ${o}`);
      } else if (o !== n) {
        removed++;
        added++;
        diffLines.push(`- ${o}`);
        diffLines.push(`+ ${n}`);
      }

      if (diffLines.length >= MAX_DIFF_LINES) break;
    }

    return {
      linesAdded: added,
      linesRemoved: removed,
      summary: diffLines.join("\n"),
    };
  }

  private walkFiles(dir: string, cb: (file: string) => void): void {
    for (const entry of fs.readdirSync(dir)) {
      const full = path.join(dir, entry);
      const stat = fs.statSync(full);

      if (stat.isDirectory()) {
        this.walkFiles(full, cb);
      } else {
        cb(full);
      }
    }
  }
}
