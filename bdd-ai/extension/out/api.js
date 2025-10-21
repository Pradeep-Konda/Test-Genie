"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateBDD = generateBDD;
const axios_1 = __importDefault(require("axios"));
const BASE_URL = "http://127.0.0.1:8001";
async function generateBDD(code) {
    try {
        // const formData = new FormData();
        // formData.append("source_code", code);
        const response = await axios_1.default.post(`${BASE_URL}/generate-bdd`, { source_code: code }, // ✅ send JSON
        { headers: { "Content-Type": "application/json" } });
        console.log("response:", response.data);
        return response.data;
    }
    catch (err) {
        console.error("Error generating BDD:", err);
        throw new Error(err.message);
    }
}
