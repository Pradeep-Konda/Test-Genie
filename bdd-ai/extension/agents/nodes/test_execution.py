import os
import re
import sys
import json
import subprocess
import requests
from datetime import datetime
from urllib.parse import quote
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
import xml.etree.ElementTree as ET
from .auth_handler import AuthHandler



class CurlInput(BaseModel):
    method: str
    url: str
    body: Optional[str] = None


class TestExecutionNode:

    def __init__(self, features_dir: str = "bdd_tests"):
        load_dotenv()
        self.features_dir = features_dir
        model = os.getenv("MODEL", "gpt-4.1")
        
        # Auth handler will be initialized when __call__ is invoked with project_path
        self.auth_handler: Optional[AuthHandler] = None

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
            "Your job is to:\n"
            "1) Execute API calls for Gherkin scenarios using the TestExecutor tool.\n"
            "2) Read all THEN steps.\n"
            "3) Determine PASS/FAIL strictly based on status codes and response body.\n"
            "4) Return results ONLY in the required JSON format.\n"
            "\n"
            "Follow the rules below with ZERO deviation.\n"
            "\n"
            "====================================================\n"
            "1. INPUT RULES\n"
            "====================================================\n"
            "You receive:\n"
            "- A set of Gherkin scenarios.\n"
            "- An OpenAPI YAML specification.\n"
            "\n"
            "From the OpenAPI spec:\n"
            "- Read the first server URL from 'servers:' → this is BASE_URL.\n"
            "- For any relative path (e.g., '/api/users'), prepend BASE_URL.\n"
            "- If a path already starts with http:// or https://, use it as-is.\n"
            "- NEVER invent, modify, or correct URLs.\n"
            "\n"
            "====================================================\n"
            "2. EXECUTION BEHAVIOR\n"
            "====================================================\n"
            "For every scenario:\n"
            "\n"
            "A) WHEN STEPS\n"
            "- Extract HTTP method, URL, and body.\n"
            "- Call TestExecutor with these values.\n"
            "\n"
            "B) THEN STEPS — VALIDATION LOGIC\n"
            "Apply ALL rules below:\n"
            "\n"
            "--------------------------\n"
            "STATUS VALIDATION RULES\n"
            "--------------------------\n"
            "\n"
            "1. EXACT MATCH\n"
            "   \"the response status should be 200\"\n"
            "   → PASS only if actual_status == 200\n"
            "\n"
            "2. NEGATIVE MATCH\n"
            "   \"the response status should not be 201\"\n"
            "   → PASS only if actual_status != 201\n"
            "\n"
            "3. MULTIPLE OPTIONS (OR)\n"
            "   \"the response status should be 200 or 204\"\n"
            "   → PASS if actual_status matches ANY listed value\n"
            "\n"
            "4. RANGE MATCH\n"
            "   \"the response status should be in range 200 to 299\"\n"
            "   → PASS if 200 ≤ actual_status ≤ 299\n"
            "\n"
            "5. SUCCESS / FAIL KEYWORDS\n"
            "   \"the response should succeed\" → treat as 200–299\n"
            "   \"the response should fail\" → treat as 400–599\n"
            "\n"
            "If no status expectation appears:\n"
            "→ Status check is automatically PASSED.\n"
            "\n"
            "--------------------------\n"
            "BODY VALIDATION RULES\n"
            "--------------------------\n"
            "\n"
            "1. \"the response should contain 'xyz'\"\n"
            "   → PASS only if the response body contains substring xyz\n"
            "\n"
            "2. \"the response should not contain 'error'\"\n"
            "   → PASS only if substring does NOT appear in body\n"
            "\n"
            "Body validation FAILS only if a Then step explicitly requires checking.\n"
            "\n"
            "--------------------------\n"
            "FINAL RESULT DECISION\n"
            "--------------------------\n"
            "A scenario is:\n"
            "- PASSED only if ALL checks (status + body) pass\n"
            "- FAILED if ANY check fails\n"
            "\n"
            "====================================================\n"
            "3. STRICT OUTPUT FORMAT (MANDATORY)\n"
            "====================================================\n"
            "\n"
            "You MUST output ONLY this JSON structure:\n"
            "\n"
            "{\n"
            "  \"results\": [\n"
            "    {\n"
            "      \"scenario\": string,\n"
            "      \"request_body\": string or null,\n"
            "      \"url\": string,\n"
            "      \"method\": string,\n"
            "      \"status\": number,\n"
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
            "- NEVER include explanations or markdown.\n"
            "- NEVER rename fields.\n"
            "- If ANY error occurs, output ONE result with \"result\": \"failed\".\n"
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
            
            if self.auth_handler:
                auth_headers = self.auth_handler.get_auth_headers()
                headers.update(auth_headers)
                
                # Handle API key in query params if configured
                auth_params = self.auth_handler.get_auth_query_params()
                if auth_params:
                    # Append query params to URL (URL-encode values for safety)
                    separator = "&" if "?" in url else "?"
                    param_str = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in auth_params.items())
                    url = f"{url}{separator}{param_str}"

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

        # --- Generate JUnit XML Report for CI/CD ---
        self._generate_junit_xml_report(results, output_dir, timestamp)

        # --- Calculate OpenAPI coverage ---
        coverage, uncovered = self._calculate_openapi_coverage(state.feature_text, state.analysis)
        
        # --- Get authentication info ---
        auth_info = "No authentication"
        if self.auth_handler and self.auth_handler.is_authenticated():
            auth_info = self.auth_handler.get_auth_summary()

        html_output = [
            "<html><head><title>API Test Report</title>",
            "<style>",
            "body{font-family:Arial;}table{width:100%;border-collapse:collapse;}",
            "th,td{border:1px solid #ccc;padding:6px;}",
            ".passed{color:green;font-weight:bold;}",
            ".failed{color:red;font-weight:bold;}",
            ".body{font-color:white;}",
            ".auth-info{background:#f0f7ff;padding:10px;border-radius:5px;margin-bottom:15px;}",
            "</style>",
            "</head><body id ='body'>",

            "<h2>API Test Execution Report</h2>",
            f"<p>Generated: {timestamp}</p>",
            f"<div class='auth-info'><strong>Authentication:</strong> {html.escape(auth_info)}</div>",
            f"<h3>Test Coverage: {coverage:.2f}%</h3>",

            # --------------------------------
            # ⭐ TABLE STARTS HERE
            # --------------------------------
            "<table id='resultsTable'>",

            "<tr>"
            "<th>S.No</th>"
            "<th>Scenario</th>"
            "<th>Request Body</th>"
            "<th>Response</th>"
            "<th>Status Code</th>"
            "<th>HTTP Request</th>"
            "<th>Method</th>"
            "<th>"
            "Result<br>"
            "<select id='resultFilter' onchange='filterResults()'>"
            "<option value='all'>All</option>"
            "<option value='passed'>Passed</option>"
            "<option value='failed'>Failed</option>"
            "</select>"
            "</th>"
            "</tr>",
        ]

        # --------------------------------
        # TABLE ROWS
        # --------------------------------
        for idx, r in enumerate(results):
            scenario = r.get("scenario", "N/A")
            request_body = r.get("request_body", "N/A")

            status = r.get("response", r.get("error", "N/A"))
            status_code = r.get("status", "N/A")
            http_request = r.get("url", "N/A")
            method = r.get("method", "N/A")

            result_flag = r.get("result", "N/A")
            color = "green" if result_flag == "passed" else "red"

            html_output.append(
                f"<tr>"
                f"<td>{idx + 1}</td>"
                f"<td>{scenario}</td>"
                f"<td><code>{request_body}</code></td>"
                f"<td>{html.escape(str(status))}</td>"
                f"<td>{status_code}</td>"
                f"<td><code>{http_request}</code></td>"
                f"<td>{method}</td>"
                f"<td style='font-weight:bold; color:{color}'>{result_flag.upper()}</td>"
                f"</tr>"
            )

        # Close table
        html_output.append("</table>")

        # --------------------------------
        # ⭐ JAVASCRIPT FILTER
        # --------------------------------
        html_output.append("""
        <script>
        function filterResults() {
            let filter = document.getElementById('resultFilter').value;
            let table = document.getElementById('resultsTable');
            let rows = table.getElementsByTagName('tr');

            for (let i = 1; i < rows.length; i++) {
                let resultCell = rows[i].getElementsByTagName('td')[7];
                if (!resultCell) continue;

                let result = resultCell.textContent.trim().toLowerCase();

                if (filter === 'all' || filter === result) {
                    rows[i].style.display = '';
                } else {
                    rows[i].style.display = 'none';
                }
            }
        }
        </script>
        """)

        # --------------------------------
        # Uncovered endpoints
        # --------------------------------
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
    # JUnit XML Report Generator
    # ------------------------------------------------------------------
    def _generate_junit_xml_report(self, results: List[Dict], output_dir: str, timestamp: str) -> Optional[str]:
        """
        Generates a JUnit XML report for CI/CD integration.
        
        Args:
            results: List of test result dictionaries
            output_dir: Directory to save the report
            timestamp: Timestamp string for filename
            
        Returns:
            Path to the generated XML file, or None if generation failed
        """
        try:
            total_tests = len(results)
            failures = sum(1 for r in results if r.get("result", "").lower() == "failed")
            
            testsuites = ET.Element("testsuites")
            testsuites.set("name", "BDD API Tests")
            testsuites.set("tests", str(total_tests))
            testsuites.set("failures", str(failures))
            testsuites.set("errors", "0")
            testsuites.set("time", "0")  
            
            testsuite = ET.SubElement(testsuites, "testsuite")
            testsuite.set("name", "API Test Execution")
            testsuite.set("tests", str(total_tests))
            testsuite.set("failures", str(failures))
            testsuite.set("errors", "0")
            testsuite.set("skipped", "0")
            testsuite.set("timestamp", datetime.now().isoformat())
            
            for idx, r in enumerate(results):
                scenario = r.get("scenario", f"Test_{idx + 1}")
                result_flag = r.get("result", "failed").lower()
                method = r.get("method", "N/A")
                url = r.get("url", "N/A")
                status_code = r.get("status", "N/A")
                response = r.get("response", r.get("error", "N/A"))
                request_body = r.get("request_body", "")
                
                testcase = ET.SubElement(testsuite, "testcase")
                testcase.set("name", scenario)
                testcase.set("classname", f"API.{method}")
                testcase.set("time", "0")  # Placeholder for execution time
                
                if result_flag == "failed":
                    failure = ET.SubElement(testcase, "failure")
                    failure.set("message", f"API call failed: {method} {url} returned {status_code}")
                    failure.set("type", "AssertionError")
                    
                    failure_details = [
                        f"Scenario: {scenario}",
                        f"Method: {method}",
                        f"URL: {url}",
                        f"Status Code: {status_code}",
                        f"Request Body: {request_body}",
                        f"Response: {str(response)[:500]}"  
                    ]
                    failure.text = "\n".join(failure_details)
                
                system_out = ET.SubElement(testcase, "system-out")
                system_out.text = f"Request: {method} {url}\nStatus: {status_code}\nResponse: {str(response)[:1000]}"
            
            xml_string = ET.tostring(testsuites, encoding="unicode", method="xml")
            
            xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string
            
            xml_path = os.path.join(output_dir, f"api_test_report_{timestamp}.xml")
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
            
            print(f"[TEST] JUnit XML report saved: {xml_path}", file=sys.stderr, flush=True)
            
            return xml_path
            
        except Exception as e:
            print(f"[TEST] Warning: Failed to generate JUnit XML report: {e}", file=sys.stderr, flush=True)
            return None
    
    
    # ------------------------------------------------------------------
    # CORE EXECUTION
    # ------------------------------------------------------------------
    def __call__(self, state, batch_size: int = 5):
        try:
            self.auth_handler = AuthHandler(state.project_path)
            
            # Log auth status (to stderr to not interfere with JSON output)
            if self.auth_handler.is_authenticated():
                print(f"[TEST] Authentication: {self.auth_handler.get_auth_summary()}", file=sys.stderr, flush=True)
            else:
                print("[TEST] Running tests without authentication", file=sys.stderr, flush=True)
            
            openapi_dir = os.path.join(state.project_path, "output")
            filepath = self._find_latest_openapi_spec(openapi_dir)
            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.endswith((".yaml", ".yml")):
                    state.analysis = yaml.safe_load(f)
                else:
                    state.analysis = json.load(f)

            # Remove Feature: lines
            cleaned_text = re.sub(r"^\s*Feature:.*$", "", state.feature_text, flags=re.MULTILINE)

            # Remove tags like @smoke @edge @performance
            cleaned_text = re.sub(r"^\s*(?:@\w[\w-]*\s*)+", "", cleaned_text, flags=re.MULTILINE)

            # Remove comments starting with "#"
            cleaned_text = re.sub(r"^\s*#.*$", "", cleaned_text, flags=re.MULTILINE)

            cleaned_text = re.sub(r"\n{2,}", "\n", cleaned_text).strip()

            # Split using MULTILINE regex inside the pattern
            raw_scenarios = re.split(r"(?m)^\s*Scenario:\s*", cleaned_text)

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


                scenarios.append({
                    "name": scenario_name,
                    "text": full_scenario,
                })



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
                            + "\n\n".join([s["text"] for s in batch]) +
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

                #all_results.extend(parsed.get("results", []))

                returned_results = parsed.get("results", [])

                for idx, r in enumerate(returned_results):

                    all_results.append(r)



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