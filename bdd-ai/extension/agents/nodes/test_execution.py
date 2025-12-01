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
import html



class CurlInput(BaseModel):
    method: str
    url: str
    body: Optional[str] = None


class TestExecutionNode:

    def __init__(self, features_dir: str = "bdd_tests"):
        load_dotenv()
        self.features_dir = features_dir
        model = os.getenv("MODEL", "gpt-4.1")

        self.llm = ChatOpenAI(
            model=model,
            temperature=0
        )

        # ---------------------
        # Updated System Prompt
        # ---------------------
        self.system_prompt = (
            "You are an API Test Execution Agent.\n"
            "\n"
            "Follow the rules below with ZERO deviation.\n"
            "\n"
            "====================================================\n"
            "1. INPUT\n"
            "====================================================\n"
            "You receive Gherkin scenarios and an OpenAPI YAML specification.\n"
            "\n"
            "- Extract BASE_URL from the OpenAPI 'servers:' section.\n"
            "- Use ONLY the FIRST server URL.\n"
            "- For any relative path like '/api/users', prepend BASE_URL.\n"
            "- If a path already starts with http:// or https://, use it as-is.\n"
            "\n"
            "====================================================\n"
            "2. EXECUTION\n"
            "====================================================\n"
            "- For every When step → call TestExecutor.\n"
            "- For every Then step → validate status code + response body.\n"
            "- ALWAYS capture:\n"
            "   • scenario name\n"
            "   • method\n"
            "   • final full URL\n"
            "   • request body\n"
            "   • response content\n"
            "   • status code\n"
            "   • result = 'passed' or 'failed'\n"
            "\n"
            "====================================================\n"
            "3. STRICT OUTPUT FORMAT (MANDATORY)\n"
            "====================================================\n"
            "You MUST return ONLY JSON in EXACTLY the following structure:\n"
            "\n"
            "{\n"
            "  \"results\": [\n"
            "    {\n"
            "      \"scenario\": string,\n"
            "      \"request_body\": string or null,\n"
            "      \"url\": string,          # FULL FINAL URL — ALWAYS REQUIRED\n"
            "      \"method\": string,       # GET/POST/PUT/DELETE — ALWAYS REQUIRED\n"
            "      \"status\": number,       # HTTP STATUS CODE — ALWAYS REQUIRED\n"
            "      \"response\": object or string,\n"
            "      \"result\": \"passed\" | \"failed\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "\n"
            "RULES:\n"
            "- NEVER omit url.\n"
            "- NEVER omit method.\n"
            "- NEVER omit status.\n"
            "- NEVER invent endpoints.\n"
            "- NEVER rewrite URLs.\n"
            "- NEVER output explanation, markdown, or natural language.\n"
            "- NEVER output anything outside JSON.\n"
            "- If an error occurs, output a valid JSON object with result='failed'.\n"
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
            file_path = os.path.join(openapi_dir, "openapi.yaml")
            if os.path.exists(file_path):
                return file_path 
            else: 
                return None
        except Exception:
            return None
        
    # ------------------------------------------------------------------    
    # OpenAPI Traceability & Coverage
    # ------------------------------------------------------------------
    def _calculate_openapi_coverage(self, feature_text: str, spec: str):
        """
        Computes OpenAPI test coverage based on the feature file content.
        Matches endpoints + methods defined in the spec.
        """
        try:
            
            # Extract paths and methods
            defined = []
            for path, methods in spec.get("paths", {}).items():
                for method in methods.keys():
                    method = method.upper()

                    # PATH ONLY (NO SERVER HOST)
                    openapi_path_only = path.rstrip("/")

                    # Replace {param} → regex for match
                    regex_path = re.sub(r"\{[^/]+\}", r"[^/]+", openapi_path_only)

                    # Exact match (allow trailing slash & ignore query params)
                    # pattern = re.compile(rf"^{regex_path}(/)?(\?.*)?$")
                    pattern = re.compile(regex_path)

                    defined.append((method, openapi_path_only, pattern))

            defined_set = {(m, p) for (m, p, _) in defined}

            # Normalize feature file
            feature_lines = feature_text.splitlines()
            feature_lower = feature_text.lower()

            # Extract all potential URLs from feature file
            url_candidates = []
            for line in feature_lines:
                found = re.findall(r"/[^\s\"']+", line)
                url_candidates.extend(found)

            # Normalize paths (remove query params)
            normalized_candidates = []
            for u in url_candidates:
                clean = u.split("?")[0].rstrip("/")
                normalized_candidates.append(clean)

            # Coverage detection
            covered_set = set()

            for (method, openapi_path_only, pattern) in defined:
                # Check if HTTP method appears in feature text
                if method.lower() not in feature_lower:
                    continue

                # Check if any URL in feature matches this OpenAPI path
                for cand in normalized_candidates:
                    if pattern.match(cand):
                        covered_set.add((method, openapi_path_only))
                        break

            # Compute coverage
            uncovered = sorted([f"{m} {p}" for (m, p) in (defined_set - covered_set)])
            total = len(defined_set)
            covered = len(covered_set)
            coverage = (covered / total * 100) if total else 0.0

            return coverage, uncovered

        except Exception as e:
            return 0.0, [f"Coverage calculation failed: {str(e)}"]


    # ------------------------------------------------------------------
    # FAST HTTP Executor (Python requests)
    # ------------------------------------------------------------------
    def _run_curl_command(self, method: str, url: str, base_url: str, body: Optional[str] = None):
        try:
            method = method.upper()
            url = (url if url.startswith("http") else f"{base_url.rstrip('/')}/{url.lstrip('/')}")

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
                raw = response.text

                # --- CLEAN UGLY FLASK DEBUG PAGE ---
                # If Flask returns a big HTML traceback, simplify it
                if "<!DOCTYPE html>" in raw or "<html" in raw.lower():
                    # Extract only the main Python exception line
                    match = re.search(r"(KeyError:.*?)(<|$)", raw, re.DOTALL)
                    if not match:
                        match = re.search(r"(Exception:.*?)(<|$)", raw, re.DOTALL)
                    if not match:
                        match = re.search(r"(Error:.*?)(<|$)", raw, re.DOTALL)

                    if match:
                        content = match.group(1).strip()
                    else:
                        content = f"HTTP {response.status_code} Error"
                else:
                    content = raw


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
        coverage, uncovered = self._calculate_openapi_coverage(state.feature_text, state.analysis)

        html_output = [
            "<html><head><title>API Test Report</title>",
            "<style>body{font-family:Arial;}table{width:100%;border-collapse:collapse;}"
            "th,td{border:1px solid #ccc;padding:6px;}</style>",
            "</head><body>",
            f"<h2>API Test Execution Report</h2><p>Generated: {timestamp}</p>",
            f"<h3>Test Coverage: {coverage:.2f}%</h3>",
            "<table><tr><th>S.No</th><th>Scenario</th><th>Request Body</th><th>Response</th><th>Status Code</th><th>HTTP Request</th><th>Method</th></tr>"
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
            html_output.append(
                f"<tr>"
                f"<td>{idx + 1}</td>"
                f"<td>{scenario}</td>"
                f"<td><code>{request_body}</code></td>"
                f"<td>{html.escape(str(status))}</td>"
                f"<td>{status_code}</td>"
                f"<td><code>{http_request}</code></td>"
                f"<td>{method}</td>"
                f"</tr>"
            )

        html_output.append("</table></body></html>")

        # --- Display uncovered endpoints if any ---
        if uncovered:
            html_output.append("<h2>Uncovered Endpoints from OpenAPI Spec</h2><ul>")
            for ep in uncovered:
                html_output.append(f"<li>{ep}</li>")
            html_output.append("</ul>")

       
        full_html = "\n".join(html_output)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        return json.dumps({"execution_output": full_html})
    
    
    # ------------------------------------------------------------------
    # CORE EXECUTION
    # ------------------------------------------------------------------
    def __call__(self, state, batch_size: int = 5):
        try:
            openapi_dir = os.path.join(state.project_path, "output")
            filepath = self._find_latest_openapi_spec(openapi_dir)
            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.endswith((".yaml", ".yml")):
                    state.analysis = yaml.safe_load(f)
                else:
                    state.analysis = json.load(f)

            # Split using MULTILINE regex inside the pattern
            raw_scenarios = re.split(r"(?m)^\s*Scenario:\s*", state.feature_text)

            scenarios = []
            for chunk in raw_scenarios:
                chunk = chunk.strip()
                if not chunk:
                    continue

                # First line = scenario name
                lines = chunk.split("\n")
                scenario_name = lines[0].strip()

                # Rest of lines form the body (Given/When/Then)
                scenario_body = "\n".join(lines[1:]).strip()

                # Rebuild scenario in proper gherkin format
                full_scenario = f"Scenario: {scenario_name}\n{scenario_body}"

                scenarios.append(full_scenario)

            all_results = []
            all_curls = []

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
                        if getattr(msg, "type", None) == "ai"
                        or msg.__class__.__name__ == "AIMessage"
                    ]
                    content = ai_messages[-1].content.strip() if ai_messages else ""
                elif hasattr(result, "content"):
                    content = result.content.strip()
                elif isinstance(result, str):
                    content = result.strip()
                else:
                    content = str(result).strip()

                # Fix: Extract JSON safely even if extra text is added
                try:
                    parsed = json.loads(content)
                except:
                    # Greedy JSON extractor: handles nested content reliably
                    match = re.search(r"\{(?:[^{}]|(?R))*\}", content, re.DOTALL)
                    if not match:
                        parsed = None
                    else:
                        parsed = json.loads(match.group(0))

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
            state.execution_output = {"error": str(e)}

        return state