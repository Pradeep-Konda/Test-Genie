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
import glob
import yaml
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from typing import List, Optional, Any, Dict


class CurlInput(BaseModel):
    method: str
    url: str
    body: Optional[str] = None

# class ReportInput(BaseModel):
#     project_path: str
#     results: List[Dict[str, Any]]
#     curl_commands: List[str] = []



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
            StructuredTool.from_function(
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
    # Tool 1: Find latest openapi spec from output
    # ------------------------------------------------------------------
    def _find_latest_openapi_spec(self, openapi_dir: str):
        """Finds the newest OpenAPI spec file (.yaml or .json) in the outputs directory."""
        try:
            candidates = glob.glob(os.path.join(openapi_dir, "openapi_*.*"))
            if not candidates:
                return None

            latest = max(candidates, key=os.path.getmtime)
            return latest
        except Exception as e:
            return None
        
    

    # ------------------------------------------------------------------
    # Tool 1: Curl Execution Engine
    # ------------------------------------------------------------------
    def _run_curl_command(self, method: str, url: str, body: Optional[str] = None):
        """
        Structured Curl executor that takes separate args (for StructuredTool).
        Returns a dict (not JSON string) so agent tooling can serialize naturally.
        """
        try:
            m = method.upper()
            # If URL is relative (e.g., starts with '/'), leave as-is; the environment should resolve host
            cmd = ["curl", "-s", "-X", m, url, "-w", "\nHTTP_STATUS:%{http_code}\n"]
            if body:
                cmd += ["-H", "Content-Type: application/json", "-d", body]

            # run curl
            result = subprocess.run(cmd, capture_output=True, text=True)
            stdout = result.stdout or ""
            stderr = result.stderr or ""

            # Extract HTTP status
            status_match = re.search(r"HTTP_STATUS:(\d+)", stdout)
            status = int(status_match.group(1)) if status_match else None
            response_body = re.sub(r"HTTP_STATUS:\d+", "", stdout).strip()

            return {
                "url": url,
                "method": m,
                "status": status,
                "response": response_body,
                "curl_command": " ".join(cmd),
                "stderr": stderr if stderr else None,
            }
        # except subprocess.TimeoutExpired:
        #     return {"error": f"Request timed out for {url}"}
        except Exception as e:
            return {"error": str(e)}



    # ------------------------------------------------------------------
    # Tool 2: HTML Report Generator
    # ------------------------------------------------------------------
    def _generate_html_report(self, state, input_json: str):
        """Generates an HTML test execution report."""
        project_path = state.project_path
        output_dir = os.path.join(project_path, "test_reports")
        os.makedirs(output_dir, exist_ok=True)
        

        try:
            data = json.loads(input_json)
            results = data.get("results", [])
            curl_commands = data.get("curl_commands", [])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = os.path.join(output_dir, f"api_test_report_{timestamp}.html")

            openapi_dir = os.path.join(project_path, "output")

            
             # --- Calculate OpenAPI coverage ---
            openapi_path = self._find_latest_openapi_spec(openapi_dir)
            coverage, uncovered = self._calculate_openapi_coverage(state.feature_text, openapi_path)

            # --- Build HTML ---
            html = [
                "<html><head><title>API Test Report</title>",
                "<style>body{font-family:Arial;margin:20px;}table{width:100%;border-collapse:collapse;}"
                "th,td{border:1px solid #ccc;padding:8px;text-align:left;}th{background:#f2f2f2;}"
                ".pass{color:green;font-weight:bold;}.fail{color:red;font-weight:bold;}</style>",
                "</head><body>",
                f"<h1>API Test Execution Report</h1><p>Generated: {timestamp}</p>",
                f"<h3>Test Coverage: {coverage:.2f}%</h3>",
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

            html.append("</table>")

            # --- Display uncovered endpoints if any ---
            if uncovered:
                html.append("<h2>Uncovered Endpoints from OpenAPI Spec</h2><ul>")
                for ep in uncovered:
                    html.append(f"<li>{ep}</li>")
                html.append("</ul>")

            html.append("</body></html>")

            full_html = "\n".join(html)

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(full_html)

            return json.dumps({"execution_output": full_html})

        except Exception as e:
            return json.dumps({"error": str(e)})
        
        
    # ------------------------------------------------------------------    
    # OpenAPI Traceability & Coverage
    # ------------------------------------------------------------------
    def _calculate_openapi_coverage(self, features, openapi_path: str):

        try:
            if not openapi_path or not os.path.exists(openapi_path):
                return 0.0, []

            # Auto-load YAML or JSON
            with open(openapi_path, "r", encoding="utf-8") as f:
                if openapi_path.endswith((".yaml", ".yml")):
                    spec = yaml.safe_load(f)
                else:
                    spec = json.load(f)

            base_path = ""
            servers = spec.get("servers", [])
            if servers and isinstance(servers, list):
                url = servers[0].get("url")
                if isinstance(url, str):
                    base_path = url.rstrip("/") 

            defined = []
            for path, methods in spec.get("paths", {}).items():
                for method in methods.keys():

                    # Apply base_path ⇒ "/api" + "/users/"
                    full_path = f"{base_path}{path}"

                    # Convert OpenAPI params → regex
                    regex_path = re.sub(r"\{[^/]+\}", r"[^/]+", full_path)

                    # Build regex (allow exact or trailing slash match)
                    pattern = re.compile(rf"{regex_path}(/)?")
                    defined.append((method.upper(), full_path, pattern))

            # Use state.features instead of reading any files
            feature_text = features if isinstance(features, str) else "\n".join(features)

            executed_matches = set()

            for method, full_path, pattern in defined:

                # Method must appear anywhere in scenario
                if method in feature_text:
                    # Search for matching URL usage
                    if pattern.search(feature_text):
                        executed_matches.add((method, full_path))

            # Compute coverage
            defined_set = {(m, p) for m, p, _ in defined}
            executed_set = set(executed_matches)

            uncovered = sorted([f"{m} {p}" for (m, p) in (defined_set - executed_set)])
            coverage = (len(executed_set) / len(defined_set) * 100) if defined_set else 0.0

            return coverage, uncovered

        except Exception as e:
            return 0.0, []


    # ------------------------------------------------------------------
    # Execute All Scenarios in Batches → ONE combined report
    # ------------------------------------------------------------------
    def __call__(self, state, batch_size: int = 5):
        try:
            scenarios = [s.strip() for s in re.split(r"\bScenario:", state.feature_text) if s.strip()]
            if not scenarios:
                raise ValueError("No scenarios found in feature files")


            all_results = []
            all_curls = []

            for i in range(0, len(scenarios), batch_size):
                batch = scenarios[i:i + batch_size]

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
                else:
                    print(f"⚠️ Could not parse AI output as JSON for batch {i//batch_size + 1}. Skipping...")

            # ✅ Generate one combined HTML report for all batches
            report_input = json.dumps({"results": all_results, "curl_commands": all_curls})
            report_json = self._generate_html_report(state, report_input)
            report_html = json.loads(report_json).get("execution_output")

           
            state.execution_output = report_html
        except Exception as e:
            state.execution_output = {"error": str(e)}
        return state
