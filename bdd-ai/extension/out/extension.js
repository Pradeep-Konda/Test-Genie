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
const vscode = __importStar(require("vscode"));
const api_1 = require("./api");
const panel_1 = require("./panel");
function activate(context) {
    const disposable = vscode.commands.registerCommand("extension.generateBDD", async () => {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            vscode.window.showErrorMessage("❌ No workspace folder open!");
            return;
        }
        const workspacePath = workspaceFolders[0].uri.fsPath;
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "🔍 Generating BDD Tests...",
        }, async () => {
            try {
                console.log("📂 Sending workspace path for analysis:", workspacePath);
                const result = await (0, api_1.generateTests)(workspacePath);
                const panel = panel_1.BDDPanel.show(result.feature_text || "No tests generated");
                panel.onDidClickRun(async () => {
                    const updatedFeatureText = panel.getFeatureText();
                    vscode.window.withProgress({
                        location: vscode.ProgressLocation.Notification,
                        title: "🏃 Running Tests...",
                    }, async () => {
                        const execResult = await (0, api_1.executeTests)(workspacePath, updatedFeatureText);
                        vscode.window.showInformationMessage("✅ Test Execution Complete!");
                        panel.showOutput(execResult.execution_output || "No output");
                    });
                });
            }
            catch (err) {
                vscode.window.showErrorMessage(`❌ Error: ${err.message}`);
            }
        });
    });
    context.subscriptions.push(disposable);
}
//# sourceMappingURL=extension.js.map