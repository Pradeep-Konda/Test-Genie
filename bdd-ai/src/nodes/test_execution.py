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




class TestExecutionNode:
    """
    Executes Gherkin-based API test scenarios using a cURL-driven REST engine via an AI agent.
    Runs all scenarios in batches but generates ONE combined HTML report at the end.
    """

    def __init__(self, features_dir: str = "bdd_tests"):
        load_dotenv()
        self.features_dir = features_dir

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
            "Return structured JSON only: { 'results': [...], 'curl_commands': [...] }.\n"
            "Never fabricate data or call fake endpoints."
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
    def _generate_html_report(self, project_path: str, input_json: str):
        """Generates an HTML test execution report."""

        output_dir = os.path.join(project_path, "test_reports")
        os.makedirs(output_dir, exist_ok=True)

        try:
            data = json.loads(input_json)
            results = data.get("results", [])
            curl_commands = data.get("curl_commands", [])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = os.path.join(output_dir, f"api_test_report_{timestamp}.html")

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
                response_code = r.get("response_code", "N/A")
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
    def _extract_scenarios(self, project_path: str) -> list:
        features_path = os.path.join(project_path, self.features_dir)
        files = [
            os.path.join(features_path, f)
            for f in os.listdir(features_path)
            if f.endswith(".feature")
        ]
        all_text = ""
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                all_text += "\n\n--- " + os.path.basename(path) + " ---\n" + f.read()
        return [s.strip() for s in re.split(r"\bScenario:", all_text) if s.strip()]

    # ------------------------------------------------------------------
    # Execute All Scenarios in Batches → ONE combined report
    # ------------------------------------------------------------------
    def __call__(self, state, batch_size: int = 5):
        try:
            scenarios = self._extract_scenarios(state.project_path)
            if not scenarios:
                raise ValueError("No scenarios found in feature files")

            #print(f"🧩 Found {len(scenarios)} scenarios — running in batches of {batch_size}")

            all_results = []
            all_curls = []

            for i in range(0, len(scenarios), batch_size):
                batch = scenarios[i:i + batch_size]
                #print(f"\n🚀 Executing batch {i//batch_size + 1}: {len(batch)} scenarios")

                batch_text = "\n\n".join(batch)
                messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=(
                        "Execute these API test scenarios using CurlExecutor.\n"
                        "Return only valid JSON in this format:\n"
                        "{ \"results\": [...], \"curl_commands\": [...] }\n\n"
                        f"{batch_text}"
                    )),
                ]

                result = self.agent.invoke({"messages": messages})

                # Try to extract JSON directly from agent output (inline logic)
                if hasattr(result, "content"):
                    content = result.content
                elif isinstance(result, dict) and "messages" in result:
                    ai_msgs = [
                        m for m in result["messages"]
                        if getattr(m, "type", None) == "ai" or m.__class__.__name__ == "AIMessage"
                    ]
                    content = ai_msgs[-1].content if ai_msgs else str(result)
                else:
                    content = str(result)

                content = content.strip()

                # Try direct JSON parse first
                parsed = None
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    # Inline regex-based fallback (no function)
                    match = re.search(r"\{(?:[^{}]|(?R))*\}", content, re.DOTALL)
                    if match:
                        try:
                            parsed = json.loads(match.group(0))
                        except Exception:
                            parsed = None

                if parsed:
                    all_results.extend(parsed.get("results", []))
                    all_curls.extend(parsed.get("curl_commands", []))
                    #print(f"✅ Batch {i//batch_size + 1} parsed successfully ({len(parsed.get('results', []))} results).")
                else:
                    print(f"⚠️ Could not parse AI output as JSON for batch {i//batch_size + 1}. Skipping...")

            # ✅ Generate one combined HTML report for all batches
            #print("\n🧾 Generating final combined HTML report...")
            report_input = json.dumps({"results": all_results, "curl_commands": all_curls})
            report_json = self._generate_html_report(state.project_path, report_input)
            report_path = json.loads(report_json).get("html_report")

            #print(f"\n🎉 All batches executed successfully!")
            #print(f"📄 Combined HTML report: {report_path}")

            state.execution_output = f"All test batches executed successfully. Combined report at {report_path}."
        except Exception as e:
            print(f"⚠️ Test Execution Error: {e}")
            state.execution_output = {"error": str(e)}
        return state

