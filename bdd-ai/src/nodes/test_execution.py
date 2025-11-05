import os
import re
import json
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


class TestExecutionNode:
    """
    Executes Gherkin-based API test scenarios using a cURL-driven REST engine via an AI agent.
    Automatically runs all scenarios in batches and lets the agent call GenerateHTMLReport internally.
    """

    def __init__(self, features_dir: str = "behave_tests/features", output_dir: str = "test_results"):
        self.features_dir = features_dir
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir

        # Initialize LLM
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

        # Tools
        self.tools = [
            Tool(
                name="CurlExecutor",
                func=self._run_curl_command,
                description=(
                    "Executes HTTP requests using curl. "
                    "Input JSON: { 'method': 'GET/POST/PUT/DELETE', 'url': '<endpoint>', "
                    "'body': '<json string or null>' }. "
                    "Returns JSON: { 'url', 'method', 'status', 'response', 'curl_command' }."
                ),
            ),
            Tool(
                name="GenerateHTMLReport",
                func=self._generate_html_report,
                description=(
                    "Generates a visual HTML test report. Input JSON: "
                    "{ 'results': [...], 'curl_commands': [...] } and returns the HTML file path."
                ),
            ),
        ]

        # System prompt
        self.system_prompt = (
            "You are an intelligent API Test Executor Agent.\n"
            "You receive Gherkin test cases and execute them step by step using CurlExecutor.\n"
            "For each 'When' step, call CurlExecutor to run the API.\n"
            "Use 'Then' steps to verify response codes and body content.\n"
            "Store the result for each scenario including:\n"
            "  { scenario, steps, status, response_code, curl_command }\n"
            "After finishing a batch, automatically call GenerateHTMLReport with all results and curl commands "
            "to generate an HTML test report.\n"
            "Never fabricate data or call fake endpoints.\n"
            "Return a JSON response summarizing the generated HTML report path."
        )

        # Create agent
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt,
        )

    # ------------------------------------------------------------------
    # Tool 1: Curl Execution Engine
    # ------------------------------------------------------------------
    def _run_curl_command(self, input_json: str):
        """Executes a REST API call using curl."""
        try:
            data = json.loads(input_json)
            method = data.get("method", "GET").upper()
            url = data.get("url")
            body = data.get("body")

            if not url:
                return json.dumps({"error": "URL missing"})

            cmd = ["curl", "-s", "-X", method, url, "-w", "\nHTTP_STATUS:%{http_code}\n"]
            if body:
                cmd += ["-H", "Content-Type: application/json", "-d", body]

            result = subprocess.run(cmd, capture_output=True, text=True)
            stdout = result.stdout

            status_match = re.search(r"HTTP_STATUS:(\d+)", stdout)
            status = int(status_match.group(1)) if status_match else None
            response_body = re.sub(r"HTTP_STATUS:\d+", "", stdout).strip()

            return json.dumps({
                "url": url,
                "method": method,
                "status": status,
                "response": response_body,
                "curl_command": " ".join(cmd),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # Tool 2: HTML Report Generator
    # ------------------------------------------------------------------
    def _generate_html_report(self, input_json: str):
        """Generates an HTML test execution report."""
        try:
            data = json.loads(input_json)
            results = data.get("results", [])
            curl_commands = data.get("curl_commands", [])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = os.path.join(self.output_dir, f"api_test_report_{timestamp}.html")

            html = [
                "<html><head><title>API Test Report</title>",
                "<style>body{font-family:Arial;margin:20px;}table{width:100%;border-collapse:collapse;}"
                "th,td{border:1px solid #ccc;padding:8px;text-align:left;}th{background:#f2f2f2;}"
                ".pass{color:green;font-weight:bold;}.fail{color:red;font-weight:bold;}</style>",
                "</head><body>",
                f"<h1>API Test Execution Report</h1><p>Generated: {timestamp}</p>",
                "<table><tr><th>Scenario</th><th>Status</th><th>Response Code</th><th>cURL Command</th></tr>",
            ]

            for r in results:
                scenario = r.get("scenario", "Unknown Scenario")
                status = r.get("status", "UNKNOWN")
                curl_cmd = r.get("curl_command", "N/A")
                response_code = r.get("status", "N/A")
                html.append(
                    f"<tr><td>{scenario}</td><td class='{status.lower()}'>{status}</td>"
                    f"<td>{response_code}</td><td><code>{curl_cmd}</code></td></tr>"
                )

            html.append("</table><h2>Executed cURL Commands</h2><ul>")
            for cmd in curl_commands:
                html.append(f"<li><code>{cmd}</code></li>")
            html.append("</ul></body></html>")

            with open(html_path, "w", encoding="utf-8") as f:
                f.write("\n".join(html))

            print(f"📄 HTML report generated at: {html_path}")
            return json.dumps({"html_report": html_path})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ------------------------------------------------------------------
    # Helper: Extract all scenarios
    # ------------------------------------------------------------------
    def _extract_scenarios(self):
        files = [
            os.path.join(self.features_dir, f)
            for f in os.listdir(self.features_dir)
            if f.endswith(".feature")
        ]
        all_text = ""
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                all_text += "\n\n--- " + os.path.basename(path) + " ---\n" + f.read()
        return [s.strip() for s in re.split(r"\bScenario:", all_text) if s.strip()]

    # ------------------------------------------------------------------
    # Execute All Scenarios in Batches
    # ------------------------------------------------------------------
    def __call__(self, state, batch_size: int = 5):
        try:
            scenarios = self._extract_scenarios()
            if not scenarios:
                raise ValueError("No scenarios found in feature files")

            print(f"🧩 Found {len(scenarios)} scenarios — running in batches of {batch_size}")

            for i in range(0, len(scenarios), batch_size):
                batch = scenarios[i:i + batch_size]
                print(f"\n🚀 Executing batch {i//batch_size + 1}: {len(batch)} scenarios")

                batch_text = "\n\n".join(batch)
                messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=f"Execute these API test scenarios and call GenerateHTMLReport when done:\n\n{batch_text}"),
                ]

                result = self.agent.invoke({"messages": messages})

                # Extract agent output
                if isinstance(result, dict) and "messages" in result:
                    ai_msgs = [m for m in result["messages"] if getattr(m, "type", None) == "ai"]
                    output = ai_msgs[-1].content if ai_msgs else ""
                elif hasattr(result, "content"):
                    output = result.content
                else:
                    output = str(result)

                print("✅ Batch execution complete.")
                print(output[:1000])  # partial preview

            print("\n🎉 All batches executed successfully!")
            state.execution_output = "All test batches executed successfully. Check generated HTML reports."
        except Exception as e:
            print(f"⚠️ Test Execution Error: {e}")
            state.execution_output = {"error": str(e)}
        return state
