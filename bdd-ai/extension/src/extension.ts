import * as vscode from "vscode";
import { generateTests, executeTests } from "./api";
import { BDDPanel } from "./panel";

export function activate(context: vscode.ExtensionContext) {
  const disposable = vscode.commands.registerCommand(
    "extension.generateBDD",
    async () => {
      const workspaceFolders = vscode.workspace.workspaceFolders;

      if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showErrorMessage("❌ No workspace folder open!");
        return;
      }

      const workspacePath = workspaceFolders[0].uri.fsPath; // Full directory path

      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "🔍 Generating BDD Tests (Analyzing entire workspace)...",
        },
        async () => {
          try {
            console.log("📂 Sending workspace path for analysis:", workspacePath);

            const result = await generateTests(workspacePath);
            const panel = BDDPanel.show(result.feature_text || "No tests generated");

            // ✅ Run tests from same workspace directory
            panel.onDidClickRun(async () => {
              vscode.window.withProgress(
                {
                  location: vscode.ProgressLocation.Notification,
                  title: "🏃 Running Tests...",
                },
                async () => {
                  const execResult = await executeTests(workspacePath);
                  vscode.window.showInformationMessage("✅ Test Execution Complete!");
                  panel.showOutput(execResult.execution_output || "No output");
                }
              );
            });
          } catch (err: any) {
            vscode.window.showErrorMessage(`❌ Error: ${err.message}`);
          }
        }
      );
    }
  );

  context.subscriptions.push(disposable);
}
