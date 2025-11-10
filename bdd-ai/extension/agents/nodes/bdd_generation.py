import os
import re
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage


class BDDGenerationNode:
    """
    AI-powered generator that converts OpenAPI specs into Gherkin (BDD) test cases
    covering happy path, edge, negative, security, and performance scenarios.
    Also generates mock data for schema-compliant test execution.
    """

    def __init__(self, output_dir: str = "behave_tests/features"):
        load_dotenv()

        # ✅ Use deterministic but strong model
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

        # ✅ Define fallback tool
        self.tools = [
            Tool(
                name="OpenAPItoAdvancedBDDGenerator",
                func=self._mock_bdd_generator,
                description=(
                    "Converts OpenAPI 3.0 specification into detailed Gherkin (BDD) tests "
                    "covering functional, edge, negative, security, and performance scenarios."
                )
            )
        ]

        # ✅ Stronger system prompt per spec 4.2–4.3
        self.system_prompt = (
            "You are a Senior QA Engineer specializing in Behavior-Driven Development (BDD) "
            "and AI-assisted API testing. Your job is to convert the given OpenAPI 3.0 YAML "
            "into comprehensive Gherkin test scenarios.\n\n"
            "Follow these rules strictly:\n"
            "1 Output must be in **pure Gherkin syntax** — no markdown, no explanations.\n"
            "2 Each `Feature:` corresponds to an API resource or module.\n"
            "3 Each endpoint must include:\n"
            "   - **Happy Path**: Valid request and successful response.\n"
            "   - **Edge Cases**: Boundary values, nulls, optional params, etc.\n"
            "   - **Negative/Error**: Invalid input, missing fields, auth failure, etc.\n"
            "   - **Security**: OWASP API Security Top 10 vulnerabilities (e.g., Injection, Broken Auth).\n"
            "   - **Performance**: Assertions on latency or response time.\n"
            "4 Generate schema-compliant **mock data** for each request body.\n"
            "5 Use clear, readable step wording: Given / When / Then.\n"
            "6 Do not omit any endpoint.\n"
            "7 Start the response directly with `Feature:` — no text before that."
        )

        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt
        )

    def _mock_bdd_generator(self, openapi_spec: str) -> str:
        """Fallback generator for when LLM fails."""
        return """Feature: Default API Endpoint
  Scenario: Happy Path
    Given an API endpoint "/example"
    When I send a valid POST request
    Then I should receive a 200 OK response

  Scenario: Negative Path
    Given an API endpoint "/example"
    When I send invalid data
    Then I should receive a 400 Bad Request response
"""

    def save_feature_files(self, project_path: str, feature_text: str) -> list:
        output_dir = os.path.join(project_path, "bdd_tests")
        os.makedirs(output_dir, exist_ok=True)

        # Clean up old files first
        for file in os.listdir(output_dir):
            if file.endswith(".feature"):
                os.remove(os.path.join(output_dir, file))

        # Split on 'Feature:' and rebuild each block properly
        features = feature_text.split("Feature:")
        written_files = []

        for index, feature in enumerate(features):
            feature = feature.strip()
            if not feature:
                continue

            # Reconstruct full block
            block = "Feature: " + feature

            # Extract readable name from first line
            match = re.match(r"Feature:\s*(.+)", block)
            if match:
                name = re.sub(r"\s+", "_", match.group(1).strip().lower())
            else:
                name = f"feature_{index}"

            # Construct file path
            file_path = os.path.join(output_dir, f"{name}.feature")

            # Write to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(block)

            written_files.append(file_path)

        return written_files

    def __call__(self, state):
        """Main pipeline entry — converts OpenAPI YAML into BDD tests."""
        openapi_spec = getattr(state, "analysis", None)
        if not openapi_spec or not openapi_spec.strip():
            feature_text = self._mock_bdd_generator("")
            state.feature_text = feature_text
            state.feature_files = self.save_feature_files(feature_text)
            return state

        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(
                    content=f"Generate advanced BDD test cases (in Gherkin) for this OpenAPI 3.0 spec:\n\n{openapi_spec}"
                )
            ]

            result = self.agent.invoke({"messages": messages})

            # 🧠 Normalize outputs like CodeAnalysisNode
            if isinstance(result, dict) and "messages" in result:
                ai_messages = [
                    msg for msg in result["messages"]
                    if getattr(msg, "type", None) == "ai" or msg.__class__.__name__ == "AIMessage"
                ]
                feature_text = ai_messages[-1].content.strip() if ai_messages else ""
            elif hasattr(result, "content"):
                feature_text = result.content.strip()
            elif isinstance(result, str):
                feature_text = result.strip()
            else:
                feature_text = str(result or "").strip()

        except Exception as e:
            print(f"⚠️ LLM Error in BDDGenerationNode: {e}")
            feature_text = self._mock_bdd_generator(openapi_spec)

        written_files = self.save_feature_files(state.project_path, feature_text)

        state.feature_text = feature_text
        #state.feature_files = written_files
        return state