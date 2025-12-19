import * as vscode from "vscode";

export class BDDPanel {
  private currentFilePath: string | null = null;
  static currentPanel: BDDPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private featureText: string = "";

  setFilePath(filePath: string) {
  this.currentFilePath = filePath;
}

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
            if (this.featureText){
              vscode.commands.executeCommand(
                "extension.executeBDD", 
                this.featureText, 
                BDDPanel.currentPanel);
            }
            else {
              vscode.window.showErrorMessage("❌ Cannot Run: No featureText detected.");
            }
            break;

          case "generateBDD":
            vscode.commands.executeCommand("extension.generateBDD");
            break;


          case "save":
            if (this.currentFilePath) {
              vscode.commands.executeCommand(
                "extension.saveThisFeature",
                this.currentFilePath,
                this.featureText
              );
            } else {
              vscode.window.showErrorMessage("❌ Cannot save: No file path detected.");
            }
            break;
          case "saveVersion":
            vscode.commands.executeCommand("extension.saveVersionFolder");
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
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    BDDPanel.currentPanel = new BDDPanel(panel, featureText);
    BDDPanel.currentPanel.update(featureText);
    return BDDPanel.currentPanel;
  }

  onDidClickRun(callback: (featureText: string) => void) {
    this._onRunClicked = callback;
  }

  getFeatureText(): string {
    return this.featureText;
  }

  showOutput(output: string) {
    this.panel.webview.postMessage({ type: "output", output });
  }

  private update(featureText: string) {
    this.featureText = featureText;
    this.panel.webview.postMessage({
      type: "setFeatureText",
      text: featureText,
    });
  }

  private dispose() {
    BDDPanel.currentPanel = undefined;
    this.panel.dispose();
  }

  private getHtml(featureText: string): string {
    const escaped = featureText
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(
        /(Feature:|Scenario:|Given |When |Then |And )/g,
        `<span class="keyword">$1</span>`
      );

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
            height: 60vh;
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

          .button-row {
              display: flex;
              justify-content: space-between;
              align-items: center;
              margin-top: 12px;
          }

          .left-buttons {
              display: flex;
              gap: 10px;
          }

          .right-buttons {
              display: flex;
              gap: 10px;
          }

          .top-right-btn {
          position: absolute;
          top: 16px;
          right: 16px;
          padding: 6px 14px;
          border-radius: 6px;
          background-color: var(--vscode-button-background);
          color: var(--vscode-button-foreground);
          border: none;
          cursor: pointer;
          font-weight: bold;
          z-index: 1000;
        }

        .top-right-btn:hover {
          background-color: var(--vscode-button-hoverBackground);
        }
        </style>
      </head>
      <body>
        <h2>Generated Test Cases</h2>
        <pre id="featureText" contenteditable="true">${escaped}</pre>

        <button id="generateBddTop" class="top-right-btn">⚙ Generate BDD</button>

        <div class="button-row">
          <div class="left-buttons">
              <button id="runTests">▶ Run Tests</button>
          </div>

          

          <div class="right-buttons">
              <button id="saveFeature">💾 Save</button>
              <button id="saveVersion">📦 Save Version</button>
          </div>
        </div>


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

          document.getElementById('saveFeature').addEventListener('click', () => {
            vscode.postMessage({ type: 'save' });
          });

          document.getElementById('saveVersion').addEventListener('click', () => {
            vscode.postMessage({ type: 'saveVersion' });
          });

          document.getElementById('generateBddTop').addEventListener('click', () => {
            vscode.postMessage({ type: 'generateBDD' });
        });


          window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.type === 'setFeatureText') {
                featureTextEl.innerText = message.text;
              }

            if (message.type === 'output') {
              const iframeHtml = '<iframe id="reportFrame" style="width:100%; height:100%; border:none;"></iframe>';
              outputEl.innerHTML = iframeHtml;

              const iframe = document.getElementById('reportFrame');

              // Minimal CSS for iframe to normalize base styles without overriding report theme
              const forcedCss =
                '<style>' +
                'html, body { margin: 0; padding: 0; }' +
                '</style>';


              const out = (message.output || '').toString().trim();

              try {
                // If output looks like a URL (starts with http/https), load it by src
                if (/^https?:\\/\\//i.test(out)) {
                  // NOTE: cross-origin pages cannot be styled from the parent. If the server returns a URL,
                  // you cannot inject CSS unless the page is same-origin or the server itself includes the CSS.
                  iframe.src = out;
                } else {
                  // Insert style into the HTML string itself so it's present from first paint.
                  let modified = out;
                  if (/<\\/head\\s*>/i.test(modified)) {
                    modified = modified.replace(/<\\/head\\s*>/i, forcedCss + '</head>');
                  } else if (/^\\s*<!DOCTYPE/i.test(modified) || /^\\s*<html/i.test(modified)) {
                    // Page has html but no head close — try to inject head
                    modified = modified.replace(/<html[^>]*>/i, (m) => m + '<head>' + forcedCss + '</head>');
                  } else {
                    // Fallback: just prepend a head with style
                    modified = '<head>' + forcedCss + '</head>' + modified;
                  }

                  // Finally set srcdoc (this will render the modified HTML including the forced CSS)
                  iframe.srcdoc = modified;
                }
              } catch (err) {
                // Fallback: set srcdoc unmodified and try a late injection (may fail if cross-origin)
                console.error('iframe injection error', err);
                iframe.srcdoc = out;
                iframe.onload = () => {
                  try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    if (iframeDoc && iframeDoc.head) {
                      const style = iframeDoc.createElement('style');
                      style.innerHTML = 'html, body { margin: 0; padding: 0; }';
                      iframeDoc.head.appendChild(style);
                    }
                  } catch (e) {
                    console.error('late iframe style injection failed', e);
                  }
                };
              }
            }
          

        });

        </script>
      </body>
      </html>
    `;
  }
}
