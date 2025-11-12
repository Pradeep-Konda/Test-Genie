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
        const panel = vscode.window.createWebviewPanel("bddPreview", "AI-Generated BDD Tests", vscode.ViewColumn.One, {
            enableScripts: true,
            retainContextWhenHidden: true,
        });
        const newPanel = new BDDPanel(panel, featureText);
        BDDPanel.currentPanel = newPanel;
        return newPanel;
    }
    onDidClickRun(callback) {
        this._onRunClicked = callback;
    }
    getFeatureText() {
        return this.featureText;
    }
    showOutput(output) {
        this.panel.webview.postMessage({ type: "output", output });
    }
    update(featureText) {
        this.featureText = featureText;
        this.panel.webview.html = this.getHtml(featureText);
    }
    dispose() {
        BDDPanel.currentPanel = undefined;
        this.panel.dispose();
    }
    getHtml(featureText) {
        const escaped = featureText
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/(Feature:|Scenario:|Given |When |Then |And )/g, `<span class="keyword">$1</span>`);
        return /* html */ `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>AI-Generated BDD Tests</title>
        <style>
          :root {
            color-scheme: light dark;
          }

          body {
            font-family: var(--vscode-editor-font-family);
            font-size: var(--vscode-editor-font-size);
            color: var(--vscode-editor-foreground);
            background-color: var(--vscode-editor-background);
            padding: 16px;
            white-space: pre-wrap;
            overflow-y: auto;
          }

          h2 {
            color: var(--vscode-editor-foreground);
            border-bottom: 1px solid var(--vscode-editorWidget-border);
            padding-bottom: 6px;
            margin-bottom: 12px;
          }

          pre {
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-editorWidget-border);
            border-radius: 6px;
            padding: 12px;
            color: var(--vscode-editor-foreground);
            font-family: var(--vscode-editor-font-family);
            font-size: var(--vscode-editor-font-size);
            height: 60vh;
            overflow-y: auto;
            outline: none;
          }

          .keyword {
            color: var(--vscode-editor-keywordForeground, #c586c0);
            font-weight: bold;
          }

          button {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            margin-top: 12px;
          }

          button:hover {
            background-color: var(--vscode-button-hoverBackground);
          }

          #output {
            margin-top: 15px;
            background: var(--vscode-editorWidget-background);
            color: var(--vscode-editor-foreground);
            padding: 10px;
            border-radius: 6px;
            border: 1px solid var(--vscode-editorWidget-border);
            height: 30vh;
            overflow-y: auto;
          }

          .pass {
            color: var(--vscode-testing-iconPassed, #4caf50);
            font-weight: bold;
          }
          .fail {
            color: var(--vscode-testing-iconFailed, #f14c4c);
            font-weight: bold;
          }
        </style>
      </head>
      <body>
        <h2>Generated Test Cases</h2>
        <pre id="featureText" contenteditable="true">${escaped}</pre>
        <button id="runTests">▶ Run Tests</button>
        <div id="output"></div>

        <script>
          const vscode = acquireVsCodeApi();
          const featureTextEl = document.getElementById('featureText');
          const outputEl = document.getElementById('output');

          featureTextEl.addEventListener('input', () => {
            vscode.postMessage({ type: 'updateText', text: featureTextEl.innerText });
          });

          document.getElementById('runTests').addEventListener('click', () => {
            vscode.postMessage({ type: 'run' });
          });

          window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.type === 'output') {
              outputEl.innerHTML = message.output;
              outputEl.scrollTop = outputEl.scrollHeight;
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