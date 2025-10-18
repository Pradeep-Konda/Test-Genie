from openai import OpenAI
from dotenv import load_dotenv
import os


class CodeAnalysisNode:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
    
    def __call__(self, data):
        code = data.source_code
        prompt = f"""Analyze the following source code and extract possible functions or endpoints
        that require testing. Return a structured JSON list of use cases and expected behaviors.\n\n{code}"""
        resp = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": "user", "content": prompt}]
                )
        data.analysis = resp.choices[0].message.content
        return data