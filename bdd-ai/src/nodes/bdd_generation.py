import os
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


class BDDGenerationNode:
    """Generates valid Gherkin BDD test scenarios from an OpenAPI 3.0 specification using LangChain agent."""

    def __init__(self, output_dir: str = "behave_tests/features"):
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir

        # ✅ Initialize the LLM
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

        # ✅ Define fallback tool in case model fails
        self.tools = [
            Tool(
                name="OpenAPIToGherkinConverter",
                func=self._mock_bdd_generator,
                description="Converts OpenAPI 3.0 specification YAML into realistic Gherkin BDD test scenarios."
            )
        ]

        # ✅ System prompt for the agent
        self.system_prompt = (
            "You are a QA Automation Engineer skilled in Behavior-Driven Development (BDD). "
            "Your task is to convert a given OpenAPI 3.0 YAML specification into multiple realistic Gherkin scenarios.\n\n"
            "Guidelines:\n"
            "- Each `Feature:` corresponds to an API resource or module.\n"
            "- Each `Scenario:` should test a specific endpoint behavior.\n"
            "- Include both positive and negative test cases.\n"
            "- Use proper Gherkin syntax: Feature, Scenario, Given, When, Then.\n"
            "- Do NOT use markdown or explanations.\n"
            "- Start directly with the 'Feature:' keyword.\n"
            "- Ensure at least 2 scenarios per endpoint."
        )

        # ✅ Create the agent with same structure as CodeAnalysisNode
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt
        )

    def _mock_bdd_generator(self, openapi_spec: str) -> str:
        """Fallback if GPT or network fails."""
        return """Feature: Default Placeholder Feature
  Scenario: Default check
    Given an API is available
    When I send a request
    Then I receive a valid response
"""

    def save_feature_files(self, feature_text: str) -> list:
        """Save multiple feature files (split by 'Feature:')."""
        features = feature_text.split("Feature:")
        written_files = []

        for i, feature in enumerate(features):
            feature = feature.strip()
            if not feature:
                continue

            file_content = "Feature: " + feature
            file_path = os.path.join(self.output_dir, f"generated_{i}.feature")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)

            written_files.append(file_path)

        return written_files

    def __call__(self, state):
        """Generate BDD feature files from OpenAPI YAML using GPT-4.1 agent."""
        openapi_spec = getattr(state, "analysis", None)
        if not openapi_spec or not openapi_spec.strip():
            feature_text = self._mock_bdd_generator("")
            state.feature_text = feature_text
            state.feature_files = self.save_feature_files(feature_text)
            return state

        try:
            # ✅ Construct agent message sequence
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"Generate Gherkin BDD scenarios for the following OpenAPI 3.0 spec:\n\n{openapi_spec}")
            ]

            # ✅ Invoke the agent
            result = self.agent.invoke({"messages": messages})

            # ✅ Extract text properly (like CodeAnalysisNode)
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

        # ✅ Save feature files locally
        written_files = self.save_feature_files(feature_text)

        # ✅ Update pipeline state
        state.feature_text = feature_text
        #state.feature_files = written_files
        return state
