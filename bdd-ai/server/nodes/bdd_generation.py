from openai import OpenAI
import os


class BDDGenerationNode:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


    def __call__(self, data):
        prompt = f"""
        Generate valid Gherkin BDD scenarios for these use cases:
        {data.analysis}

        Rules:
        - Respond only with valid Gherkin syntax.
        - Do NOT include markdown code blocks or explanations.
        - Start directly with 'Feature:'.
        """
        resp = self.client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
        )
        feature_text = resp.choices[0].message.content

        os.makedirs("behave_tests/features", exist_ok=True)

        # 🧩 Split multiple Feature: blocks
        features = feature_text.split("Feature:")
        written_files = []

        for i, feature in enumerate(features):
            if not feature.strip():
                continue
            file_content = "Feature:" + feature.strip()
            file_path = f"behave_tests/features/generated_{i+1}.feature"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            written_files.append(file_path)

        # data.feature_files = written_files
        data.feature_text = feature_text
        return data