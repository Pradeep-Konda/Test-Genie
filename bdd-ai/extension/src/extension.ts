import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { generateTests, executeTests } from "./api";
import { BDDPanel } from "./panel";

export function activate(context: vscode.ExtensionContext) {
  // 🧩 Command to generate tests
  const generateCmd = vscode.commands.registerCommand("extension.generateBDD", async () => {
    const workspace = vscode.workspace.workspaceFolders?.[0];
    if (!workspace) {
      vscode.window.showErrorMessage("❌ No workspace folder open!");
      return;
    }

    const workspacePath = workspace.uri.fsPath;
    vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "🔍 Generating BDD Tests..." },
      async () => {
        try {
          const result = await generateTests(workspacePath);
          const panel = BDDPanel.show(result.feature_text || "No tests generated");
          panel.onDidClickRun(async () => {
            const updated = panel.getFeatureText();
            vscode.window.withProgress(
              { location: vscode.ProgressLocation.Notification, title: "🏃 Running Tests..." },
              async () => {
                const exec = await executeTests(workspacePath, updated);
                vscode.window.showInformationMessage("✅ Test Execution Complete!");
                panel.showOutput(exec.execution_output || "No output");
              }
            );
          });
        } catch (err: any) {
          vscode.window.showErrorMessage(`❌ Error: ${err.message}`);
        }
      }
    );
  });

  // 🌳 Register Feature Explorer
  const provider = new FeatureTreeDataProvider();
  const treeView = vscode.window.createTreeView("featureExplorer", { treeDataProvider: provider });
  vscode.workspace.onDidChangeWorkspaceFolders(() => provider.refresh());

  // 📂 Handle selection → show in panel
  treeView.onDidChangeSelection(async (event) => {
    const item = event.selection[0];
    if (!item) return;

    const fullPath = item.resourceUri?.fsPath;
    if (!fullPath) return;

    const stat = fs.statSync(fullPath);
    if (stat.isFile() && fullPath.endsWith(".feature")) {
      const text = fs.readFileSync(fullPath, "utf-8");
      BDDPanel.show(text);
    } else if (stat.isDirectory()) {
      const features = getFeatureFiles(fullPath);
      const combined = features.map((f) => fs.readFileSync(f, "utf-8")).join("\n\n");
      BDDPanel.show(combined || "📁 No .feature files found.");
    }
  });

  // 🧹 Register refresh command
  vscode.commands.registerCommand("featureExplorer.refresh", () => provider.refresh());

  context.subscriptions.push(generateCmd, treeView);
}

/** 🔍 Recursively collect all .feature files */
function getFeatureFiles(dir: string): string[] {
  let results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir)) {
    const full = path.join(dir, entry);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) results = results.concat(getFeatureFiles(full));
    else if (entry.endsWith(".feature")) results.push(full);
  }
  return results;
}

/** 🌳 Custom provider for Feature Explorer */
class FeatureTreeDataProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.ProviderResult<vscode.TreeItem[]> {
    const workspace = vscode.workspace.workspaceFolders?.[0];
    if (!workspace) return [];

    const baseDir = element ? element.resourceUri!.fsPath : workspace.uri.fsPath;
    if (!fs.existsSync(baseDir)) return [];

    const items: vscode.TreeItem[] = [];
    const entries = fs
      .readdirSync(baseDir)
      .filter((e) => {
        const full = path.join(baseDir, e);
        const stat = fs.statSync(full);
        return stat.isDirectory() || e.endsWith(".feature");
      })
      .sort((a, b) => {
        const aIsDir = fs.statSync(path.join(baseDir, a)).isDirectory();
        const bIsDir = fs.statSync(path.join(baseDir, b)).isDirectory();
        return aIsDir === bIsDir ? a.localeCompare(b) : aIsDir ? -1 : 1;
      });

    for (const entry of entries) {
      const full = path.join(baseDir, entry);
      const stat = fs.statSync(full);
      const isDir = stat.isDirectory();

      const item = new vscode.TreeItem(
        vscode.Uri.file(full),
        isDir
          ? vscode.TreeItemCollapsibleState.Collapsed
          : vscode.TreeItemCollapsibleState.None
      );

      item.label = entry;
      item.tooltip = `${full}\n${isDir ? "📁 Folder" : "🧩 Feature File"}${
        !isDir ? `\nSize: ${(stat.size / 1024).toFixed(1)} KB` : ""
      }`;
      item.iconPath = isDir
        ? new vscode.ThemeIcon("folder-library")
        : new vscode.ThemeIcon("symbol-keyword"); // Gherkin-like icon
      item.contextValue = isDir ? "folder" : "feature";

      items.push(item);
    }
    return items;
  }
}

export function deactivate() {}
