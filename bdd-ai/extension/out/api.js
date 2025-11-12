"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateTests = generateTests;
exports.saveUpdatedFeatureFile = saveUpdatedFeatureFile;
exports.executeTests = executeTests;
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const vscode = __importStar(require("vscode"));
/**
 * Returns the Python interpreter path currently selected in VS Code.
 * Falls back to "python" if no interpreter is set.
 */
async function getPythonPath() {
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
        const configPath = config.get("defaultInterpreterPath");
        if (configPath)
            return configPath;
        return "python";
    }
    catch {
        return "python";
    }
}
/**
 * Run the Python backend with specified phase ("generate" or "execute")
 */
async function runPython(phase, inputPath) {
    const pythonPath = await getPythonPath();
    // ✅ Use absolute path from installed extension root
    const extension = vscode.extensions.getExtension("TestGenie.vscode-bdd-ai");
    const extensionPath = extension?.extensionPath || __dirname;
    const scriptPath = path.join(extensionPath, "agents", "main.py");
    const openaiApiKey = process.env.OPENAI_API_KEY ||
        vscode.workspace.getConfiguration("bddai").get("openaiApiKey") ||
        "";
    // 🔍 Debug info (helpful in Developer Tools console)
    console.log("🐍 Python Path:", pythonPath);
    console.log("📄 Script Path:", scriptPath);
    console.log("📦 Exists:", fs.existsSync(scriptPath));
    console.log("🔑 OpenAI Key Set:", openaiApiKey ? "✅ Yes" : "❌ No");
    return new Promise((resolve, reject) => {
        const python = (0, child_process_1.spawn)(pythonPath, [scriptPath, phase, inputPath], {
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
            }
            else {
                try {
                    resolve(JSON.parse(output));
                }
                catch (e) {
                    reject(new Error("Failed to parse Python output: " + output));
                }
            }
        });
    });
}
/**
 * Generates BDD test cases by analyzing the codebase
 */
async function generateTests(workspacePath) {
    return runPython("generate", workspacePath);
}
/**
 * Clears existing .feature files in outputDir
 */
function clearOutputDir(outputDir) {
    if (!fs.existsSync(outputDir))
        return;
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
function saveUpdatedFeatureFile(workspacePath, featureText) {
    const outputDir = path.join(workspacePath, "bdd_tests");
    if (!fs.existsSync(outputDir))
        fs.mkdirSync(outputDir, { recursive: true });
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
async function executeTests(workspacePath, updatedFeatureText) {
    if (updatedFeatureText) {
        saveUpdatedFeatureFile(workspacePath, updatedFeatureText);
    }
    return runPython("execute", workspacePath);
}
//# sourceMappingURL=api.js.map