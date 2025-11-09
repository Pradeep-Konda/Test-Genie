import * as vscode from "vscode";

export class BDDPanel {
  static currentPanel: BDDPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private featureText: string = "";
  private _onRunClicked: ((featureText: string) => void) | undefined;

  private constructor(panel: vscode.WebviewPanel, featureText: string) {
    this.panel = panel;
    this.featureText = featureText;

    this.panel.webview.html = this.getHtml(featureText);

    // Listen for messages from webview
    this.panel.webview.onDidReceiveMessage(
      (message) => {
        switch (message.type) {
          case "updateText":
            this.featureText = message.text;
            break;
          case "run":
            if (this._onRunClicked) this._onRunClicked(this.featureText);
            break;
        }
      },
      undefined,
      []
    );

    this.panel.onDidDispose(() => this.dispose());
  }

  static show(featureText: string) {
    if (BDDPanel.currentPanel) {
      BDDPanel.currentPanel.panel.reveal(vscode.ViewColumn.One);
      BDDPanel.currentPanel.update(featureText);
      return BDDPanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      "bddPreview",
      "AI-Generated BDD Tests",
      vscode.ViewColumn.One,
      { enableScripts: true }
    );

    const newPanel = new BDDPanel(panel, featureText);
    BDDPanel.currentPanel = newPanel;
    return newPanel;
  }

  /**
   * Register callback when Run button is clicked
   */
  onDidClickRun(callback: (featureText: string) => void) {
    this._onRunClicked = callback;
  }

  /**
   * Get latest feature text (after user edits)
   */
  getFeatureText(): string {
    return this.featureText;
  }

  /**
   * Show test execution output
   */
  showOutput(output: string) {
    this.panel.webview.postMessage({ type: "output", output });
  }

  /**
   * Update webview content (on new test generation)
   */
  private update(featureText: string) {
    this.featureText = featureText;
    this.panel.webview.html = this.getHtml(featureText);
  }

  /**
   * Clean up
   */
  private dispose() {
    BDDPanel.currentPanel = undefined;
    this.panel.dispose();
  }

  /**
   * Generate HTML content for the panel
   */
  private getHtml(featureText: string): string {
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
