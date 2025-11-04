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

    const python = spawn(pythonPath, [scriptPath, phase, input], {
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

export async function generateTests(code: string) {
  return runPython("generate", code);
}

export async function executeTests(featureText: string) {
  return runPython("execute", featureText);
}
