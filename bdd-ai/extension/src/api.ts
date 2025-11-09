import { spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";

export interface BDDResult {
  analysis?: string;
  feature_text?: string;
  execution_output?: string;
}

/**
 * Run the Python backend with specified phase ("generate" or "execute")
 */
function runPython(phase: string, inputPath: string): Promise<BDDResult> {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, "../../src/main.py");
    const pythonPath = path.join(__dirname, "../../venv/Scripts/python.exe");

    const pythonArgs = [scriptPath, phase, inputPath];

    const python = spawn(pythonPath, pythonArgs, {
      cwd: path.join(__dirname, "../../src"),
    });

    let output = "";
    let errorOutput = "";

    python.stdout.on("data", (data) => (output += data.toString()));
    python.stderr.on("data", (data) => (errorOutput += data.toString()));

    python.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(errorOutput || "Python script failed"));
      } else {
        try {
          resolve(JSON.parse(output));
        } catch {
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

  // 🧹 Clear old feature files
  clearOutputDir(outputDir);

  // ✂️ Split by 'Feature:' while keeping the word
  const featureBlocks = featureText
    .split(/(?=Feature:)/g)
    .map(f => f.trim())
    .filter(f => f.length > 0);

  featureBlocks.forEach((block, index) => {
    // Derive a readable name
    const match = block.match(/Feature:\s*(.+)/);
    const name = match ? match[1].trim().replace(/\s+/g, "_").toLowerCase() : `feature_${index}`;
    const filePath = path.join(outputDir, `${name}.feature`);
    fs.writeFileSync(filePath, block, "utf-8");
  });

  return outputDir;
}

/**
 * Executes BDD tests from workspace (after ensuring updated file is written)
 */
export async function executeTests(workspacePath: string, updatedFeatureText?: string) {
  // 🧩 If user edited feature text in panel, persist before running tests
  if (updatedFeatureText) {
    saveUpdatedFeatureFile(workspacePath, updatedFeatureText);
  }

  return runPython("execute", workspacePath);
}
