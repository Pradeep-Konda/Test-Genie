"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const api_1 = require("./api");
const panel_1 = require("./panel");
function activate(context) {
    function getFormattedTimestamp() {
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, "0");
        const dd = String(now.getDate()).padStart(2, "0");
        const hh = String(now.getHours()).padStart(2, "0");
        const min = String(now.getMinutes()).padStart(2, "0");
        const ss = String(now.getSeconds()).padStart(2, "0");
        return `${yyyy}${mm}${dd}_${hh}${min}${ss}`;
    }
    const saveFileCmd = vscode.commands.registerCommand("extension.saveThisFeature", async (filePath, updatedText) => {
        try {
            fs.writeFileSync(filePath, updatedText, "utf8");
            vscode.window.showInformationMessage("💾 Feature file saved.");
        }
        catch (err) {
            vscode.window.showErrorMessage("❌ Failed to save feature file: " + err.message);
        }
    });
    const saveVersionFolderCmd = vscode.commands.registerCommand("extension.saveVersionFolder", async () => {
        try {
            const workspace = vscode.workspace.workspaceFolders?.[0];
            if (!workspace)
                return;
            const workspacePath = workspace.uri.fsPath;
            const bddDir = path.join(workspacePath, "bdd_tests");
            const versionsDir = path.join(workspacePath, "Versions");
            if (!fs.existsSync(versionsDir))
                fs.mkdirSync(versionsDir);
            // Create timestamped folder
            const timestamp = getFormattedTimestamp();
            const versionFolder = path.join(versionsDir, `version_${timestamp}`);
            fs.mkdirSync(versionFolder);
            // Copy all feature files
            const featureFiles = fs
                .readdirSync(bddDir)
                .filter(f => f.endsWith(".feature"));
            featureFiles.forEach(file => {
                const src = path.join(bddDir, file);
                const dest = path.join(versionFolder, file);
                fs.copyFileSync(src, dest);
            });
            vscode.window.showInformationMessage(`📦 Version saved: ${path.basename(versionFolder)}`);
        }
        catch (err) {
            vscode.window.showErrorMessage("❌ Failed to save version: " + err.message);
        }
    });
    // 🧩 Command to generate tests
    const generateCmd = vscode.commands.registerCommand("extension.generateBDD", async () => {
        const workspace = vscode.workspace.workspaceFolders?.[0];
        if (!workspace) {
            vscode.window.showErrorMessage("❌ No workspace folder open!");
            return;
        }
        const workspacePath = workspace.uri.fsPath;
        vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "🔍 Generating BDD Tests..." }, async () => {
            try {
                const result = await (0, api_1.generateTests)(workspacePath);
                const panel = panel_1.BDDPanel.show(result.feature_text || "No tests generated");
                panel.onDidClickRun(async () => {
                    const updated = panel.getFeatureText();
                    vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "🏃 Running Tests..." }, async () => {
                        const exec = await (0, api_1.executeTests)(workspacePath, updated);
                        vscode.window.showInformationMessage("✅ Test Execution Complete!");
                        panel.showOutput(exec.execution_output || "No output");
                    });
                });
            }
            catch (err) {
                vscode.window.showErrorMessage(`❌ Error: ${err.message}`);
            }
        });
    });
    // 🌳 Register Feature Explorer
    const provider = new FeatureTreeDataProvider();
    const treeView = vscode.window.createTreeView("featureExplorer", { treeDataProvider: provider });
    vscode.workspace.onDidChangeWorkspaceFolders(() => provider.refresh());
    // 📂 Handle selection → show in panel
    treeView.onDidChangeSelection(async (event) => {
        const item = event.selection[0];
        if (!item)
            return;
        const fullPath = item.resourceUri?.fsPath;
        if (!fullPath)
            return;
        const stat = fs.statSync(fullPath);
        if (stat.isFile() && fullPath.endsWith(".feature")) {
            const text = fs.readFileSync(fullPath, "utf-8");
            const panel = panel_1.BDDPanel.show(text);
            panel.setFilePath(fullPath); // <-- Add this line
        }
        else if (stat.isDirectory()) {
            const features = getFeatureFiles(fullPath);
            const combined = features.map((f) => fs.readFileSync(f, "utf-8")).join("\n\n");
            panel_1.BDDPanel.show(combined || "📁 No .feature files found.");
        }
    });
    // 🧹 Register refresh command
    vscode.commands.registerCommand("featureExplorer.refresh", () => provider.refresh());
    // context.subscriptions.push(generateCmd, treeView);
    context.subscriptions.push(generateCmd, saveFileCmd, saveVersionFolderCmd, // <-- REQUIRED
    treeView);
}
/** 🔍 Recursively collect all .feature files */
function getFeatureFiles(dir) {
    let results = [];
    if (!fs.existsSync(dir))
        return results;
    for (const entry of fs.readdirSync(dir)) {
        const full = path.join(dir, entry);
        const stat = fs.statSync(full);
        if (stat.isDirectory())
            results = results.concat(getFeatureFiles(full));
        else if (entry.endsWith(".feature"))
            results.push(full);
    }
    return results;
}
/** 🌳 Custom provider for Feature Explorer */
class FeatureTreeDataProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() {
        this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren(element) {
        const workspace = vscode.workspace.workspaceFolders?.[0];
        if (!workspace)
            return [];
        const baseDir = element ? element.resourceUri.fsPath : workspace.uri.fsPath;
        if (!fs.existsSync(baseDir))
            return [];
        const items = [];
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
            const item = new vscode.TreeItem(vscode.Uri.file(full), isDir
                ? vscode.TreeItemCollapsibleState.Collapsed
                : vscode.TreeItemCollapsibleState.None);
            item.label = entry;
            item.tooltip = `${full}\n${isDir ? "📁 Folder" : "🧩 Feature File"}${!isDir ? `\nSize: ${(stat.size / 1024).toFixed(1)} KB` : ""}`;
            item.iconPath = isDir
                ? new vscode.ThemeIcon("folder-library")
                : new vscode.ThemeIcon("symbol-keyword"); // Gherkin-like icon
            item.contextValue = isDir ? "folder" : "feature";
            items.push(item);
        }
        return items;
    }
}
function deactivate() { }
//# sourceMappingURL=extension.js.map