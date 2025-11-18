import os
import re
import json
import subprocess
import requests
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


class TestExecutionNode:

    def __init__(self, features_dir: str = "bdd_tests"):
        load_dotenv()
        self.features_dir = features_dir

        self.llm = ChatOpenAI(
            model="gpt-4.1",
            temperature=0
        )

        # ---------------------
        # Updated System Prompt
        # ---------------------
        self.system_prompt = (
            "You are an API Test Execution Agent.\n"
            "\n"
            "You strictly follow these rules:\n"
            "\n"
            "1. INPUT: You receive multiple Gherkin Scenarios.\n"
            "   - You also receive an OpenAPI YAML specification.\n"
            "   - Extract the base server URL from the OpenAPI spec:\n"
            "       * Read the 'servers:' section.\n"
            "       * Use the FIRST server URL if multiple exist.\n"
            "   - This extracted BASE_URL must be used to construct full URLs.\n"
            "\n"
            "2. PROCESS:\n"
            "   - For every 'When' step → call TestExecutor tool.\n"
            "   - Before calling the tool, prepare the final URL:\n"
            "       * If the step contains a relative path like '/api/orders', prepend BASE_URL.\n"
            "       * If the step already contains 'http' or 'https', use it as-is.\n"
            "   - For every 'Then' step → verify HTTP status & JSON fields.\n"
            "   - Capture scenario, method, final url, request body, response, status.\n"
            "\n"
            "3. OUTPUT: Return ONLY JSON in structure:\n"
            "{\n"
            "  \"results\": [...],\n"
            "}\n"
            "\n"
            "4. RULES:\n"
            "   - Never invent URLs.\n"
            "   - Never rewrite endpoints.\n"
            "   - Never output text outside JSON.\n"
            "   - Always apply BASE_URL when needed.\n"
            "   - If missing data → return JSON error.\n"
        )

        # ---------------------
        # Tools
        # ---------------------
        self.tools = [
            StructuredTool.from_function(
                name="TestExecutor",
                func=self._run_curl_command,
                description="Executes real HTTP requests.",
            )
        ]

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
    # FAST HTTP Executor (Python requests)
    # ------------------------------------------------------------------
    def _run_curl_command(self, method: str, url: str, base_url: str, body: Optional[str] = None):
        try:
            method = method.upper()
            url = (url if url.startswith("http") else f"{base_url.rstrip('/')}/{url.lstrip('/')}")
            #print(f"Executing {method} request to {url} with body: {body}")
            # if url.startswith("/"):
            #     url = f"http://localhost:5000{url}"

            headers = {"Content-Type": "application/json"}

            json_body = None
            if body:
                try:
                    json_body = json.loads(body)
                except:
                    json_body = body

            response = requests.request(
                method=method,
                url=url,
                json=json_body if isinstance(json_body, dict) else None,
                data=json_body if isinstance(json_body, str) else None,
                headers=headers,
                timeout=10
            )

            try:
                content = response.json()
            except:
                content = response.text

            return {
                "url": url,
                "method": method,
                "status": response.status_code,
                "response": content,
                "stderr": None
            }

        except Exception as e:
            return {
                "error": str(e),
                "stderr": str(e)
            }

    # ------------------------------------------------------------------
    # HTML Report Generator
    # ------------------------------------------------------------------
    def _generate_html_report(self, state, input_json: str):
        """Generates HTML report + returns the HTML content (VS Code receives it)."""
        try:
            data = json.loads(input_json)
        except Exception as e:
            return json.dumps({"error": f"Invalid report input: {str(e)}"})

        results = data.get("results", [])
        curl_cmds = data.get("curl_commands", [])

        output_dir = os.path.join(state.project_path, "test_reports")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = os.path.join(output_dir, f"api_test_report_{timestamp}.html")

        # --- Calculate OpenAPI coverage ---
        openapi_path = self._find_latest_openapi_spec(output_dir)
        coverage, uncovered = self._calculate_openapi_coverage(state.feature_text, openapi_path)

        html = [
            "<html><head><title>API Test Report</title>",
            "<style>body{font-family:Arial;}table{width:100%;border-collapse:collapse;}"
            "th,td{border:1px solid #ccc;padding:6px;}</style>",
            "</head><body>",
            f"<h2>API Test Execution Report</h2><p>Generated: {timestamp}</p>",
            f"<h3>Test Coverage: {coverage:.2f}%</h3>",
            "<table><tr><th>Scenario</th><th>Request Body</th><th>Response</th><th>Status Code</th><th>HTTP Request</th><th>Method</th></tr>"
        ]

        for idx, r in enumerate(results):
            scenario = r.get("scenario", "N/A")
            request_body = r.get("request_body", "N/A")

            status = r.get("response", r.get("error", "N/A"))

            # Determine status code
            status_code = r.get("status", "N/A")

            # Each scenario uses matching index from curl_commands
            http_request = r.get("url", "N/A")
            method = r.get("method", "N/A")
            html.append(
                f"<tr>"
                f"<td>{scenario}</td>"
                f"<td><code>{request_body}</code></td>"
                f"<td>{status}</td>"
                f"<td>{status_code}</td>"
                f"<td><code>{http_request}</code></td>"
                f"<td>{method}</td>"
                f"</tr>"
            )

        html.append("</table></body></html>")

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
    # ------------------------------------------------------------------
    # CORE EXECUTION
    # ------------------------------------------------------------------
    def __call__(self, state, batch_size: int = 5):
        try:
            scenarios = [s.strip() for s in re.split(r"\bScenario:", state.feature_text) if s.strip()]
            all_results = []
            all_curls = []

            #print(f"Total scenarios to execute: {len(scenarios)}")

            for i in range(0, len(scenarios), batch_size):
                batch = scenarios[i:i + batch_size]

                messages = [
                            SystemMessage(content=self.system_prompt),
                            HumanMessage(
                                content=(
                                    "Execute these scenarios and return only JSON.\n"
                                    "\n"
                                    "----- OPENAPI SPEC START -----\n"
                                    f"{state.analysis}\n"
                                    "----- OPENAPI SPEC END -----\n"
                                    "\n"
                                    "----- SCENARIOS START -----\n"
                                    + "\n\n".join(batch) +
                                    "\n----- SCENARIOS END -----"
                                )
                            ),
                        ]



                result = self.agent.invoke({"messages": messages})

                if isinstance(result, dict) and "messages" in result:
                    ai_messages = [
                        msg for msg in result["messages"]
                        if getattr(msg, "type", None) == "ai" or msg.__class__.__name__ == "AIMessage"
                    ]
                    content = ai_messages[-1].content.strip() if ai_messages else ""
                elif hasattr(result, "content"):
                    content = result.content.strip()
                elif isinstance(result, str):
                    content = result.strip()
                else:
                    content = str(result or "").strip()
                
                #print("Agent Response Content:", content)

                # Extract JSON safely
                try:
                    parsed = json.loads(content)
                except:
                    match = re.search(r"\{(?:[^{}]|(?R))*\}", content, re.DOTALL)
                    parsed = json.loads(match.group(0)) if match else None

                if not parsed:
                    all_results.append({"error": "Agent returned invalid JSON"})
                    continue

                all_results.extend(parsed.get("results", []))
                all_curls.extend(parsed.get("curl_commands", []))

            final_input = json.dumps({
                "results": all_results,
                "curl_commands": all_curls
            })

            report_json = self._generate_html_report(state, final_input)
            state.execution_output = json.loads(report_json).get("execution_output")

        except Exception as e:
            state.execution_output = {
                "error": str(e)
            }

        return state
