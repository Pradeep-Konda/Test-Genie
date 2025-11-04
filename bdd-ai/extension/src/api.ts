import { spawn } from "child_process";
import * as path from "path";

export interface BDDResult {
  analysis?: string;
  feature_text?: string;
  execution_output?: string;
}

function runPython(phase: string, input: string): Promise<BDDResult> {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, "../../src/main.py");
    const pythonPath = path.join(__dirname, "../../venv/Scripts/python.exe");

    const pythonArgs = [scriptPath, phase, input, "--dir"];

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

export async function generateTests(workspacePath: string) {
  return runPython("generate", workspacePath);
}

export async function executeTests(featureText: string) {
  return runPython("execute", featureText);
}
