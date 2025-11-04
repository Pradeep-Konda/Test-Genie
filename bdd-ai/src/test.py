import os
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage
from dotenv import load_dotenv

load_dotenv()

# Load your OpenAI API key
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# ---------- TOOL DEFINITIONS ----------

def analyze_codebase(codebase_path: str) -> str:
    """Read the given codebase and extract OpenAPI spec."""
    # In real use, you'd parse routes/controllers
    return f"Generated OpenAPI spec for {codebase_path}"

def generate_bdd_tests(openapi_spec: str) -> str:
    """Generate BDD test scenarios from OpenAPI spec."""
    return f"Generated BDD test cases based on spec: {openapi_spec[:200]}..."

def execute_tests(test_scenarios: str) -> str:
    """Simulate test execution and create HTML report."""
    html_report = f"""
    <html>
    <head><title>BDD Test Report</title></head>
    <body>
        <h1>BDD Test Execution Report</h1>
        <p>Executed tests:</p>
        <pre>{test_scenarios}</pre>
        <p>Status: ✅ All tests passed successfully.</p>
    </body>
    </html>
    """
    with open("bdd_test_report.html", "w", encoding="utf-8") as f:
        f.write(html_report)
    return "HTML report written to bdd_test_report.html"

# ---------- TOOL REGISTRATION ----------

code_analysis_tools = [
    Tool(
        name="CodeBaseAnalyzer",
        func=analyze_codebase,
        description="Analyzes codebase and generates OpenAPI specification."
    )
]

bdd_generation_tools = [
    Tool(
        name="BDDTestGenerator",
        func=generate_bdd_tests,
        description="Generates BDD test scenarios from an OpenAPI spec."
    )
]

test_execution_tools = [
    Tool(
        name="BDDTestExecutor",
        func=execute_tests,
        description="Executes BDD test scenarios and produces HTML report."
    )
]

# ---------- AGENT CREATION ----------

llm = ChatOpenAI(model="gpt-4.1", temperature=0)

code_analysis_agent = create_agent(
    model=llm,
    tools=code_analysis_tools,
)

bdd_generation_agent = create_agent(
    model=llm,
    tools=bdd_generation_tools,
)

test_execution_agent = create_agent(
    model=llm,
    tools=test_execution_tools,
)

# ---------- SYSTEM PROMPTS ----------
system_prompts = {
    "code_analysis": SystemMessage(
        content="You are a code analysis expert. Read the provided codebase path and output an OpenAPI spec."
    ),
    "bdd_generation": SystemMessage(
        content="You are a BDD test designer. Take the OpenAPI spec and produce detailed Gherkin-style test cases."
    ),
    "test_execution": SystemMessage(
        content="You are a QA automation tester. Execute reviewed BDD tests and produce an HTML test report."
    )
}

# ---------- LANGGRAPH ORCHESTRATION ----------

def run_pipeline(codebase_path: str):
    print("🔍 Running Code Analysis Agent...")
    spec = code_analysis_agent.invoke({
        "input": f"{system_prompts['code_analysis'].content}\nCodebase Path: {codebase_path}"
    })["output"]

    print("🧪 Running BDD Generation Agent...")
    tests = bdd_generation_agent.invoke({
        "input": f"{system_prompts['bdd_generation'].content}\nOpenAPI Spec: {spec}"
    })["output"]

    print("👨‍💻 Waiting for Human Review...")
    input("Press Enter after reviewing and updating test scenarios...")

    print("🚀 Running Test Execution Agent...")
    report = test_execution_agent.invoke({
        "input": f"{system_prompts['test_execution'].content}\nTest Scenarios: {tests}"
    })["output"]

    print("✅ Pipeline complete!")
    print(report)


if __name__ == "__main__":
    run_pipeline("C:/Users/Pradeepkonda/Desktop/repos/test-genie/demo-flask-service")