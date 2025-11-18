import { spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as vscode from "vscode";

export interface BDDResult {
  analysis?: string;
  feature_text?: string;
  execution_output?: string;
}

/**
 * Returns the Python interpreter path currently selected in VS Code.
 * Falls back to "python" if no interpreter is set.
 */
async function getPythonPath(): Promise<string> {
  try {
    const pythonExtension = vscode.extensions.getExtension("ms-python.python");

    if (pythonExtension) {
      if (!pythonExtension.isActive) {
        await pythonExtension.activate();
      }
      const execDetails = pythonExtension.exports?.environment?.getExecutionDetails?.();
      if (execDetails?.execCommand && execDetails.execCommand.length > 0) {
        return execDetails.execCommand[0];
      }
    }

    const config = vscode.workspace.getConfiguration("python");
    const configPath = config.get<string>("defaultInterpreterPath");
    if (configPath) return configPath;

    return "python";
  } catch {
    return "python";
  }
}

/**
 * Run the Python backend with specified phase ("generate" or "execute")
 */
async function runPython(
  phase: string,
  inputPath: string,
  updatedFeatureText?: string,
  analysis?: string
): Promise<BDDResult> {
  const pythonPath = await getPythonPath();

  // Use absolute path from installed extension root
  const extension = vscode.extensions.getExtension("TestGenie.vscode-bdd-ai");
  const extensionPath = extension?.extensionPath || __dirname;
  const scriptPath = path.join(extensionPath, "agents", "main.py");

  const openaiApiKey =
    process.env.OPENAI_API_KEY ||
    (vscode.workspace.getConfiguration("bddai").get("openaiApiKey") as string) ||
    "";

  // Debug info
  console.log("🐍 Python Path:", pythonPath);
  console.log("📄 Script Path:", scriptPath);
  console.log("📦 Exists:", fs.existsSync(scriptPath));
  console.log("🔑 OpenAI Key Set:", openaiApiKey ? "✅ Yes" : "❌ No");

  return new Promise((resolve, reject) => {
    // ✅ Build args safely (no undefined allowed)
    const args: string[] = [scriptPath, phase, inputPath];

    if (updatedFeatureText) args.push(updatedFeatureText);
    if (analysis) args.push(analysis);

    console.log("⚙️ Running with args:", args);

    // Final safeguard (filters out accidental undefined/null)
    const safeArgs = args.filter((a): a is string => typeof a === "string");

    const python = spawn(pythonPath, safeArgs, {
      cwd: path.dirname(scriptPath),
      env: {
        ...process.env,
        OPENAI_API_KEY: openaiApiKey,
      },
    });

    let output = "";
    let errorOutput = "";

    python.stdout.on("data", (data) => {
      const text = data.toString();
      output += text;
      console.log("🐍 stdout:", text);
    });

    python.stderr.on("data", (data) => {
      const text = data.toString();
      errorOutput += text;
      console.error("🐍 stderr:", text);
    });

    python.on("close", (code) => {
      console.log("📤 Python process exited with code:", code);
      if (code !== 0) {
        reject(new Error(errorOutput || "Python script failed"));
      } else {
        try {
          resolve(JSON.parse(output));
        } catch (e) {
          reject(new Error("Failed to parse Python output: " + output));
        }
      }
    });
  });
}

/**
 * Generates BDD test cases by analyzing the codebase
 */
export async function generateTests(workspacePath: string) {
  return runPython("generate", workspacePath);
}

/**
 * Clears existing .feature files in outputDir
 */
function clearOutputDir(outputDir: string) {
  if (!fs.existsSync(outputDir)) return;
  const files = fs.readdirSync(outputDir);
  for (const file of files) {
    const filePath = path.join(outputDir, file);
    if (fs.lstatSync(filePath).isFile() && file.endsWith(".feature")) {
      fs.unlinkSync(filePath);
    }
  }
}

/**
 * Saves updated feature text back into the workspace output folder
 */
export function saveUpdatedFeatureFile(workspacePath: string, featureText: string): string {
  const outputDir = path.join(workspacePath, "bdd_tests");
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

  clearOutputDir(outputDir);

  const featureBlocks = featureText
    .split(/(?=Feature:)/g)
    .map((f) => f.trim())
    .filter((f) => f.length > 0);

  featureBlocks.forEach((block, index) => {
    const match = block.match(/Feature:\s*(.+)/);
    const name = match
      ? match[1].trim().replace(/\s+/g, "_").toLowerCase()
      : `feature_${index}`;
    const filePath = path.join(outputDir, `${name}.feature`);
    fs.writeFileSync(filePath, block, "utf-8");
  });

  return outputDir;
}

/**
 * Executes BDD tests from workspace (after ensuring updated file is written)
 */
export async function executeTests(
  workspacePath: string,
  updatedFeatureText?: string,
  analysis?: string
) {
  return runPython("execute", workspacePath, updatedFeatureText, analysis);
}
