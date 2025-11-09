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
/**
 * Run the Python backend with specified phase ("generate" or "execute")
 */
function runPython(phase, inputPath) {
    return new Promise((resolve, reject) => {
        const scriptPath = path.join(__dirname, "../../src/main.py");
        const pythonPath = path.join(__dirname, "../../venv/Scripts/python.exe");
        const pythonArgs = [scriptPath, phase, inputPath];
        const python = (0, child_process_1.spawn)(pythonPath, pythonArgs, {
            cwd: path.join(__dirname, "../../src"),
        });
        let output = "";
        let errorOutput = "";
        python.stdout.on("data", (data) => (output += data.toString()));
        python.stderr.on("data", (data) => (errorOutput += data.toString()));
        python.on("close", (code) => {
            if (code !== 0) {
                reject(new Error(errorOutput || "Python script failed"));
            }
            else {
                try {
                    resolve(JSON.parse(output));
                }
                catch {
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
async function executeTests(workspacePath, updatedFeatureText) {
    // 🧩 If user edited feature text in panel, persist before running tests
    if (updatedFeatureText) {
        saveUpdatedFeatureFile(workspacePath, updatedFeatureText);
    }
    return runPython("execute", workspacePath);
}
