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
exports.BDDPanel = void 0;
const vscode = __importStar(require("vscode"));
class BDDPanel {
    constructor(panel) {
        this._panel = panel;
    }
    static show(content) {
        const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
        if (BDDPanel.currentPanel) {
            BDDPanel.currentPanel._panel.reveal(column);
            BDDPanel.currentPanel._panel.webview.html = BDDPanel.getHtml(content);
            return;
        }
        const panel = vscode.window.createWebviewPanel("bddView", "BDD Test Results", column, { enableScripts: true });
        BDDPanel.currentPanel = new BDDPanel(panel);
        panel.webview.html = BDDPanel.getHtml(content);
        panel.onDidDispose(() => {
            BDDPanel.currentPanel = undefined;
        });
    }
    static getHtml(content) {
        return `<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <style>
        body { font-family: Arial, sans-serif; padding: 1rem; background: #121212; color: #eee; }
        pre { background: #1e1e1e; padding: 1rem; border-radius: 8px; overflow-x: auto; }
      </style>
    </head>
    <body>
      <h2>Generated BDD Feature</h2>
      <pre>${content}</pre>
    </body>
    </html>`;
    }
}
exports.BDDPanel = BDDPanel;
