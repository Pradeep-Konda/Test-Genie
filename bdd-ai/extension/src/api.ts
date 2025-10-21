import axios from "axios";

const BASE_URL = "http://127.0.0.1:8001";

export async function generateBDD(code: string) {
  try {
    // const formData = new FormData();
    // formData.append("source_code", code);

    const response = await axios.post(
      `${BASE_URL}/generate-bdd`,
      { source_code: code }, // ✅ send JSON
      { headers: { "Content-Type": "application/json" } }
    );

    console.log("response:", response.data);

    return response.data;
  } catch (err: any) {
    console.error("Error generating BDD:", err);
    throw new Error(err.message);
  }
}
