from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import PythonFunctionTool
import subprocess
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# --- Define Tools --- #

def code_analysis_tool(code: str) -> str:
    prompt = f"""
Analyze this Python code and extract possible functions, classes, or API-like behaviors
that need automated testing. Return a structured JSON list of use cases.

Code:
{code}
"""
    resp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content

code_analysis = PythonFunctionTool(
    name="CodeAnalysis",
    description="Analyze Python code and output JSON of functions and behaviors",
    func=code_analysis_tool
)

def bdd_generation_tool(analysis: str) -> str:
    prompt = f"Generate Gherkin BDD scenarios for these use cases:\n{analysis}"
    resp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
    )
    feature_text = resp.choices[0].message.content
    os.makedirs("behave_tests/features", exist_ok=True)
    feature_file_path = "behave_tests/features/generated.feature"
    with open(feature_file_path, "w") as f:
        f.write(feature_text)
    return feature_text

bdd_generation = PythonFunctionTool(
    name="BDDGeneration",
    description="Convert code analysis into BDD feature files",
    func=bdd_generation_tool
)

def test_execution_tool(feature_file_path: str) -> str:
    result = subprocess.run(
        ["behave", feature_file_path],
        capture_output=True,
        text=True
    )
    return result.stdout

test_execution = PythonFunctionTool(
    name="TestExecution",
    description="Execute a Behave feature file and return results",
    func=test_execution_tool
)

# --- Initialize Agent --- #
llm = ChatOpenAI(model_name="gpt-4.1", openai_api_key=api_key)

tools = [code_analysis, bdd_generation, test_execution]

agent = create_agent(
    tools=tools,
    llm=llm,
    agent="zero-shot-react-description",
    verbose=True
)

# --- Example Run --- #
def run_workflow(code_content: str):
    # Step 1: Analyze code
    analysis_result = code_analysis_tool(code_content)

    # Step 2: Generate BDD
    feature_file = bdd_generation_tool(analysis_result)

    # Step 3: Execute tests
    test_result = test_execution_tool("behave_tests/features/")

    return {"feature": feature_file, "result": test_result}
