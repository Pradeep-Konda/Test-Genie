import os
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


class CodeAnalysisNode:
    """Analyzes all source code files in a project and produces a valid OpenAPI spec."""

    def __init__(self, output_dir: str = "outputs"):
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir

        # ✅ Initialize GPT model
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

        # ✅ Tool for reading code files recursively
        def read_project_code(directory: str) -> str:
            """Reads all backend-related source code files in a project."""
            combined_code = ""
            supported_exts = (".py", ".js", ".ts", ".java", ".go", ".cs")

            for root, _, files in os.walk(directory):
                for f in files:
                    if f.endswith(supported_exts):
                        file_path = os.path.join(root, f)
                        try:
                            with open(file_path, "r", encoding="utf-8") as file:
                                combined_code += f"\n\n# File: {file_path}\n{file.read()}"
                        except Exception:
                            continue
            return combined_code or "No readable code files found."

        self.tools = [
            Tool(
                name="ReadProjectFiles",
                func=read_project_code,
                description="Recursively read all source code files from a project directory."
            )
        ]

        # ✅ Define system prompt
        self.system_prompt = (
            "You are a senior backend architect. "
            "You will first use the `ReadProjectFiles` tool to read all source files in the provided directory. "
            "Then, identify all HTTP endpoints defined using frameworks such as Flask, FastAPI, Express.js, Spring Boot, ASP.NET, Go Gin, etc. "
            "Generate a **valid OpenAPI 3.0 YAML** that includes:\n"
            "- Title, version, and base path\n"
            "- Every detected endpoint and HTTP method\n"
            "- Request body (if any)\n"
            "- Query/path parameters\n"
            "- Example JSON responses (if visible)\n\n"
            "If the source defines no explicit endpoints, output an empty `paths: {}` section. "
            "Return **only** the YAML. Do not add explanations or Markdown."
        )

        # ✅ Create LangChain Agent
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt
        )

    def _mock_analyzer(self, _: str) -> str:
        """Fallback YAML."""
        return """openapi: 3.0.0
info:
  title: Auto Generated API
  version: 1.0.0
paths: {}
"""

    def save_openapi_file(self, yaml_content: str) -> str:
        """Save generated OpenAPI YAML to disk."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(self.output_dir, f"openapi_{timestamp}.yaml")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
        return file_path

    def __call__(self, state):
        """Analyze the codebase in the given project path using GPT-4.1."""
        if not getattr(state, "project_path", None):
            state.analysis = self._mock_analyzer("")
            return state

        try:
            # Construct message list
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"Use the ReadProjectFiles tool on this directory: {state.project_path}")
            ]

            # Run the agent
            result = self.agent.invoke({"messages": messages})

            yaml_text = ""

            # Extract YAML from agent output
            if isinstance(result, dict) and "messages" in result:
                ai_msgs = [
                    m for m in result["messages"]
                    if getattr(m, "type", None) == "ai" or m.__class__.__name__ == "AIMessage"
                ]
                yaml_text = ai_msgs[-1].content if ai_msgs else ""
            elif hasattr(result, "content"):
                yaml_text = result.content
            elif isinstance(result, str):
                yaml_text = result
            else:
                yaml_text = str(result or "")

            yaml_text = yaml_text.strip()
        except Exception as e:
            print(f"⚠️ LLM Error: {e}")
            yaml_text = self._mock_analyzer("")

        # Save + update state
        state.analysis = yaml_text
        self.save_openapi_file(yaml_text)
        return state
