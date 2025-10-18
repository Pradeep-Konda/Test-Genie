import * as vscode from "vscode";

export class BDDPanel {
  public static currentPanel: BDDPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;

  private constructor(panel: vscode.WebviewPanel) {
    this._panel = panel;
  }

  public static show(content: string) {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : vscode.ViewColumn.One;

    if (BDDPanel.currentPanel) {
      BDDPanel.currentPanel._panel.reveal(column);
      BDDPanel.currentPanel._panel.webview.html = BDDPanel.getHtml(content);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      "bddView",
      "BDD Test Results",
      column,
      { enableScripts: true }
    );

    BDDPanel.currentPanel = new BDDPanel(panel);
    panel.webview.html = BDDPanel.getHtml(content);

    panel.onDidDispose(() => {
      BDDPanel.currentPanel = undefined;
    });
  }

  private static getHtml(content: string): string {
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
