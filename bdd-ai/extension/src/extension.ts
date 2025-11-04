import * as vscode from "vscode";
import { generateTests, executeTests } from "./api";
import { BDDPanel } from "./panel";

export function activate(context: vscode.ExtensionContext) {
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
        { location: vscode.ProgressLocation.Notification, title: "Generating Tests..." },
        async () => {
          try {
            console.log("Generating BDD tests...", code);
            const result = await generateTests(code);
            const panel = BDDPanel.show(result.feature_text || "No tests generated");

            panel.onDidClickRun(async (modifiedFeatureText: string) => {
              vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: "Running Tests..." },
                async () => {
                  const execResult = await executeTests(modifiedFeatureText);
                  vscode.window.showInformationMessage("✅ Test Execution Complete!");
                  panel.showOutput(execResult.execution_output || "No output");
                }
              );
            });
          } catch (err: any) {
            vscode.window.showErrorMessage(`Error: ${err.message}`);
          }
        }
      );
    }
  );

  context.subscriptions.push(disposable);
}
