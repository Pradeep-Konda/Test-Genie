import os
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage


class CodeAnalysisNode:
    """Analyzes all source code files in a project and produces a valid OpenAPI spec."""

    def __init__(self):
        load_dotenv()
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

        def read_project_code(directory: str) -> str:
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

        self.system_prompt = (
    "You are a senior backend architect. "
    "You will first use the `ReadProjectFiles` tool to read all source files in the provided directory. "
    "Then, identify all HTTP endpoints defined using frameworks such as Flask, FastAPI, Express.js, "
    "Spring Boot, ASP.NET, Go Gin, Django, Laravel, etc. "
    "\n\n"
    "You MUST also detect the application's server host and port from the source code, such as:\n"
    "- Flask: app.run(host='0.0.0.0', port=5000)\n"
    "- FastAPI/Uvicorn: uvicorn.run(app, host='127.0.0.1', port=8000)\n"
    "- Express.js: app.listen(3000)\n"
    "- Spring Boot: server.port=8081\n"
    "- ASP.NET: builder.WebHost.UseUrls(\"http://localhost:5221\")\n"
    "- Go Gin: r.Run(\":8080\")\n"
    "\n"
    "Extract the **base server URL** in the form: http://host:port\n"
    "- If host is not explicitly defined, default to 127.0.0.1\n"
    "- If port is not explicitly defined, default based on framework (Flask 5000, FastAPI 8000, Express 3000)\n"
    "\n"
    "Then, generate a **valid OpenAPI 3.0 YAML** that includes:\n"
    "- openapi version\n"
    "- info → title and version\n"
    "- servers → a list containing the detected base URL\n"
    "- paths for every detected endpoint + method\n"
    "- request body schema (if detectable)\n"
    "- query/path parameters\n"
    "- JSON response examples (if visible)\n\n"
    "If the source defines no explicit endpoints, output an empty `paths: {}` section.\n"
    "Return ONLY the YAML. Do not add explanations or Markdown."
)

        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt
        )

    def _mock_analyzer(self, _: str) -> str:
        return """openapi: 3.0.0
                info:
                title: Auto Generated API
                version: 1.0.0
                paths: {}
                """

    def save_openapi_file(self, project_path: str, yaml_content: str) -> str:
        """Save generated OpenAPI YAML inside the same project folder."""
        output_dir = os.path.join(project_path, "output")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"openapi_{timestamp}.yaml"
        file_path = os.path.join(output_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
        return file_path

    def __call__(self, state):
        if not getattr(state, "project_path", None):
            state.analysis = self._mock_analyzer("")
            return state

        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"Use the ReadProjectFiles tool on this directory: {state.project_path}")
            ]

            result = self.agent.invoke({"messages": messages})

            yaml_text = ""
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

        # ✅ Save file inside the same project path
        saved_path = self.save_openapi_file(state.project_path, yaml_text)
        #print(f"✅ OpenAPI spec saved at: {saved_path}")

        state.analysis = yaml_text
        return state

