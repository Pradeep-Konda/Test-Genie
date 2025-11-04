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
    static show(featureText) {
        if (BDDPanel.currentPanel) {
            BDDPanel.currentPanel.panel.reveal();
            return BDDPanel.currentPanel;
        }
        const panel = vscode.window.createWebviewPanel("bddPreview", "AI-Generated BDD Tests", vscode.ViewColumn.One, { enableScripts: true });
        panel.webview.html = BDDPanel.getHtml(featureText);
        BDDPanel.currentPanel = new BDDPanel(panel);
        return BDDPanel.currentPanel;
    }
    constructor(panel) {
        this.panel = panel;
    }
    static getHtml(featureText) {
        return `
      <html>
      <body>
        <h2>Generated Test Cases</h2>
        <textarea id="featureText" style="width:100%; height:60vh;">${featureText}</textarea>
        <br/>
        <button id="runTests">Run Tests</button>
        <pre id="output"></pre>
        <script>
          const vscode = acquireVsCodeApi();
          document.getElementById('runTests').addEventListener('click', () => {
            const text = document.getElementById('featureText').value;
            vscode.postMessage({ type: 'run', featureText: text });
          });
        </script>
      </body>
      </html>
    `;
    }
    onDidClickRun(callback) {
        this.panel.webview.onDidReceiveMessage((message) => {
            if (message.type === "run")
                callback(message.featureText);
        });
    }
    showOutput(output) {
        this.panel.webview.postMessage({ type: "output", output });
    }
}
exports.BDDPanel = BDDPanel;
