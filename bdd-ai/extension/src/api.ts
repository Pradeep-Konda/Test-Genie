import { spawn } from "child_process";
import * as path from "path";

export interface BDDResult {
  analysis: string;
  feature_text: string;
  execution_output: string;
}

export async function generateBDD(code: string): Promise<BDDResult> {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, "../../src/main.py");

    // Use the Python executable from your virtual environment
    const pythonPath = path.join(__dirname, "../../venv/Scripts/python.exe");

    const python = spawn(pythonPath, [scriptPath, code], {
      cwd: path.join(__dirname, "../../src"), // optional: set working dir to src
    });

    let output = "";
    let errorOutput = "";

    python.stdout.on("data", (data) => {
      output += data.toString();
    });

    python.stderr.on("data", (data) => {
      errorOutput += data.toString();
    });

    python.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(errorOutput || "Python script failed"));
      } else {
        try {
          const parsed = JSON.parse(output);
          resolve(parsed);
        } catch (err) {
          reject(new Error("Failed to parse Python output: " + output));
        }
      }
    });
  });
}
