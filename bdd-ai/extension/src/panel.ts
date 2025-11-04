import * as vscode from "vscode";

export class BDDPanel {
  static currentPanel: BDDPanel | undefined;
  private readonly panel: vscode.WebviewPanel;

  static show(featureText: string) {
    if (BDDPanel.currentPanel) {
      BDDPanel.currentPanel.panel.reveal();
      return BDDPanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      "bddPreview",
      "AI-Generated BDD Tests",
      vscode.ViewColumn.One,
      { enableScripts: true }
    );

    panel.webview.html = BDDPanel.getHtml(featureText);
    BDDPanel.currentPanel = new BDDPanel(panel);
    return BDDPanel.currentPanel;
  }

  private constructor(panel: vscode.WebviewPanel) {
    this.panel = panel;
  }

  static getHtml(featureText: string): string {
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

  onDidClickRun(callback: (featureText: string) => void) {
    this.panel.webview.onDidReceiveMessage((message) => {
      if (message.type === "run") callback(message.featureText);
    });
  }

  showOutput(output: string) {
    this.panel.webview.postMessage({ type: "output", output });
  }
}
