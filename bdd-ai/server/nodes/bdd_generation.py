from openai import OpenAI
import os


class BDDGenerationNode:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


    def __call__(self, data):
        prompt = f"Generate Gherkin BDD scenarios for these use cases:\n{data.analysis}"
        resp = self.client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
        )
        feature_text = resp.choices[0].message.content


        os.makedirs("behave_tests/features", exist_ok=True)
        with open("behave_tests/features/generated.feature", "w") as f:
            f.write(feature_text)


        data.feature_file = feature_text
        return data