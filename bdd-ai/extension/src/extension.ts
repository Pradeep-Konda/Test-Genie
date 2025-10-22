import * as vscode from "vscode";
import { BDDResult, generateBDD } from "./api";
import { BDDPanel } from "./panel";

export function activate(context: vscode.ExtensionContext) {
  console.log("✅ AI BDD Test Generator activated.");

  const disposable = vscode.commands.registerCommand(
    "extension.generateBDD",
    async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showErrorMessage("No code file open!");
        return;
      }

      const code = editor.document.getText();
      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "Generating BDD Tests...",
          cancellable: false,
        },
        async () => {
          try {
            const result: BDDResult = await generateBDD(code);
            BDDPanel.show(result.feature_text || JSON.stringify(result));
          } catch (err: any) {
            vscode.window.showErrorMessage(`Error: ${err.message}`);
          }
        }
      );
    }
  );

  context.subscriptions.push(disposable);
}

export function deactivate() {}
