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
    constructor(panel, featureText) {
        this.featureText = "";
        this.panel = panel;
        this.featureText = featureText;
        this.panel.webview.html = this.getHtml(featureText);
        // Listen for messages from webview
        this.panel.webview.onDidReceiveMessage((message) => {
            switch (message.type) {
                case "updateText":
                    this.featureText = message.text;
                    break;
                case "run":
                    if (this._onRunClicked)
                        this._onRunClicked(this.featureText);
                    break;
            }
        }, undefined, []);
        this.panel.onDidDispose(() => this.dispose());
    }
    static show(featureText) {
        if (BDDPanel.currentPanel) {
            BDDPanel.currentPanel.panel.reveal(vscode.ViewColumn.One);
            BDDPanel.currentPanel.update(featureText);
            return BDDPanel.currentPanel;
        }
        const panel = vscode.window.createWebviewPanel("bddPreview", "AI-Generated BDD Tests", vscode.ViewColumn.One, { enableScripts: true });
        const newPanel = new BDDPanel(panel, featureText);
        BDDPanel.currentPanel = newPanel;
        return newPanel;
    }
    /**
     * Register callback when Run button is clicked
     */
    onDidClickRun(callback) {
        this._onRunClicked = callback;
    }
    /**
     * Get latest feature text (after user edits)
     */
    getFeatureText() {
        return this.featureText;
    }
    /**
     * Show test execution output
     */
    showOutput(output) {
        this.panel.webview.postMessage({ type: "output", output });
    }
    /**
     * Update webview content (on new test generation)
     */
    update(featureText) {
        this.featureText = featureText;
        this.panel.webview.html = this.getHtml(featureText);
    }
    /**
     * Clean up
     */
    dispose() {
        BDDPanel.currentPanel = undefined;
        this.panel.dispose();
    }
    /**
     * Generate HTML content for the panel
     */
    getHtml(featureText) {
        const escaped = featureText.replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <style>
          body {
            font-family: sans-serif;
            padding: 10px;
          }
          h2 {
            margin-bottom: 8px;
          }
          textarea {
            width: 100%;
            height: 60vh;
            font-family: monospace;
            font-size: 14px;
            padding: 8px;
          }
          button {
            margin-top: 10px;
            background-color: #007acc;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
          }
          button:hover {
            background-color: #005fa3;
          }
          #output {
          margin-top: 15px;
          background: #f3f3f3;
          padding: 10px;
          border-radius: 6px;
          height: 30vh;
          overflow-y: auto;
          white-space: normal;
        }
        table {
            width: 100%;
            border-collapse: collapse;
          }
          th, td {
            border: 1px solid #ccc;
            padding: 8px;
            text-align: left;
          }
          th {
            background: #f2f2f2;
          }
          .pass {
            color: green;
            font-weight: bold;
          }
          .fail {
            color: red;
            font-weight: bold;
          }
        </style>
      </head>
      <body>
        <h2>Generated Test Cases</h2>
        <textarea id="featureText">${escaped}</textarea>
        <br/>
        <button id="runTests">▶ Run Tests</button>
        <button id="refreshTests" disabled>⟳ Refresh Tests (after editing)</button>
        <div id="output"></div>

        <script>
          const vscode = acquireVsCodeApi();
          const area = document.getElementById('featureText');
          const output = document.getElementById('output');

          area.addEventListener('input', () => {
            vscode.postMessage({ type: 'updateText', text: area.value });
          });

          document.getElementById('runTests').addEventListener('click', () => {
            vscode.postMessage({ type: 'run' });
          });

          window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.type === 'output') {
              output.innerHTML  = message.output;
              output.scrollTop = output.scrollHeight; // auto-scroll
            }
          });
        </script>
      </body>
      </html>
    `;
    }
}
exports.BDDPanel = BDDPanel;
//# sourceMappingURL=panel.js.map