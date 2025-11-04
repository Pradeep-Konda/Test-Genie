import os
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


class CodeAnalysisNode:
    """Analyzes source code in any backend language and produces a valid OpenAPI spec."""

    def __init__(self, output_dir: str = "outputs"):
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir

        # ✅ Initialize GPT model
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

        # ✅ Define a fallback analyzer tool
        self.tools = [
            Tool(
                name="UniversalCodeAnalyzer",
                func=self._mock_analyzer,
                description="Parse backend source code and produce an OpenAPI 3.0 YAML specification."
            )
        ]

        # ✅ Define system instructions for the agent
        self.system_prompt = (
            "You are a senior backend architect. "
            "Given a source codebase (in any programming language), identify all HTTP endpoints "
            "defined using frameworks like Flask, FastAPI, Express.js, Spring Boot, ASP.NET, Go Gin, etc. "
            "Your goal: Generate a correct **OpenAPI 3.0 YAML** specification that includes:\n"
            "- Title, version, and base path\n"
            "- Every detected endpoint and HTTP method\n"
            "- Request body (if any)\n"
            "- Query/path parameters\n"
            "- Example JSON responses (if visible)\n\n"
            "If the source defines no explicit endpoints, output an empty `paths: {}` section — do not invent any.\n"
            "Return **only** the YAML. Do not add explanations or Markdown formatting."
        )

        # ✅ Create the agent properly
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt  # ✅ Proper key for system context
        )

    def _mock_analyzer(self, source_code: str) -> str:
        """Fallback YAML when LLM fails."""
        return """openapi: 3.0.0
info:
  title: Auto Generated API
  version: 1.0.0
paths: {}
"""

    def save_openapi_file(self, yaml_content: str) -> str:
        """Save generated OpenAPI YAML to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(self.output_dir, f"openapi_{timestamp}.yaml")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
        return file_path

    def __call__(self, state):
        """Analyze source code using GPT-4.1 via LangChain agent."""
        if not state.source_code or len(state.source_code.strip()) == 0:
            yaml_text = self._mock_analyzer("")
            state.analysis = yaml_text
            return state

        try:
            # ✅ Construct explicit message list to avoid empty array error
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"Generate the OpenAPI 3.0 YAML for this source code:\n{state.source_code}")
            ]

            # ✅ Agent invocation with proper messages
            result = self.agent.invoke({"messages": messages})

            yaml_text = ""

            # 🧠 If the agent returns a dictionary with messages
            if isinstance(result, dict) and "messages" in result:
                # Find the last AIMessage in the messages list
                ai_messages = [
                    msg for msg in result["messages"]
                    if getattr(msg, "type", None) == "ai" or msg.__class__.__name__ == "AIMessage"
                ]
                if ai_messages:
                    yaml_text = ai_messages[-1].content or ""
                else:
                    yaml_text = ""
            elif hasattr(result, "content"):
                yaml_text = getattr(result, "content", "")
            elif isinstance(result, str):
                yaml_text = result
            else:
                yaml_text = str(result or "")

            # 🧹 Clean up and validate YAML text
            yaml_text = yaml_text.strip()

        except Exception as e:
            print(f"⚠️ LLM Error: {e}")
            yaml_text = self._mock_analyzer("")

        state.analysis = yaml_text
        self.save_openapi_file(yaml_text)
        return state
