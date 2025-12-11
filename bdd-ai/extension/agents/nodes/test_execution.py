import os
import re
import sys
import json
import subprocess
import requests
from datetime import datetime
from urllib.parse import quote, urlparse
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
from .auth_handler import AuthHandler
from .schema_validator import SchemaValidator



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
        
        # Schema validator for contract testing (initialized in __call__)
        self.schema_validator: Optional[SchemaValidator] = None

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

    def _extract_endpoint_path(self, url: str) -> str:
        """
        Extract the endpoint path from a full URL.
        
        Args:
            url: Full URL like "http://localhost:5000/api/users/123?foo=bar"
            
        Returns:
            Endpoint path like "/api/users/123"
        """
        try:
            parsed = urlparse(url)
            return parsed.path or "/"
        except Exception:
            return url
    

    def _validate_response_schema(
        self, 
        url: str, 
        method: str, 
        status_code: int, 
        response_body: Any
    ) -> Dict[str, Any]:
        """
        Validate API response against OpenAPI schema.
        
        Args:
            url: Full request URL
            method: HTTP method
            status_code: Response status code
            response_body: Parsed response body
            
        Returns:
            Dict with validation results
        """
        if not self.schema_validator:
            return {
                "schema_valid": True,
                "schema_found": False,
                "violations": [],
                "violation_count": 0
            }
        
        endpoint = self._extract_endpoint_path(url)
        
        try:
            result = self.schema_validator.validate_response(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                response_body=response_body
            )
            
            return {
                "schema_valid": result.is_valid,
                "schema_found": result.schema_found,
                "violations": [v.to_dict() for v in result.violations],
                "violation_count": len(result.violations)
            }
        except Exception as e:
            print(f"[SCHEMA] Validation error: {e}", file=sys.stderr)
            return {
                "schema_valid": True,
                "schema_found": False,
                "violations": [],
                "violation_count": 0,
                "error": str(e)
            }

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
        
    def _calculate_openapi_coverage(self, feature_text: str, spec: str):
        """
        Computes OpenAPI test coverage based on the feature file content.
        Matches endpoints + methods defined in the spec.
        """
        try:
            
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

            feature_lines = feature_text.splitlines()
            feature_lower = feature_text.lower()

            url_candidates = []
            for line in feature_lines:
                found = re.findall(r"/[^\s\"']+", line)
                url_candidates.extend(found)

            normalized_candidates = []
            for u in url_candidates:
                clean = u.split("?")[0].rstrip("/")
                normalized_candidates.append(clean)

            covered_set = set()

            for (method, openapi_path_only, pattern) in defined:
                if method.lower() not in feature_lower:
                    continue

                for cand in normalized_candidates:
                    if pattern.match(cand):
                        covered_set.add((method, openapi_path_only))
                        break

            uncovered = sorted([f"{m} {p}" for (m, p) in (defined_set - covered_set)])
            total = len(defined_set)
            covered = len(covered_set)
            coverage = (covered / total * 100) if total else 0.0

            return coverage, uncovered

        except Exception as e:
            return 0.0, [f"Coverage calculation failed: {str(e)}"]


    def _run_curl_command(self, method: str, url: str, base_url: str, body: Optional[str] = None):
        try:
            method = method.upper()
            url = (url if url.startswith("http") else f"{base_url.rstrip('/')}/{url.lstrip('/')}")

            headers = {"Content-Type": "application/json"}
            
            if self.auth_handler:
                auth_headers = self.auth_handler.get_auth_headers()
                headers.update(auth_headers)
                
                auth_params = self.auth_handler.get_auth_query_params()
                if auth_params:
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

        coverage, uncovered = self._calculate_openapi_coverage(state.feature_text, state.analysis)
        
        auth_info = "No authentication"
        if self.auth_handler and self.auth_handler.is_authenticated():
            auth_info = self.auth_handler.get_auth_summary()

        schema_passed = sum(1 for r in results if r.get("schema_validation", {}).get("schema_valid", True))
        schema_failed = sum(1 for r in results if r.get("schema_validation", {}).get("schema_found", False) and not r.get("schema_validation", {}).get("schema_valid", True))
        schema_not_found = sum(1 for r in results if not r.get("schema_validation", {}).get("schema_found", True))
        total_violations = sum(r.get("schema_validation", {}).get("violation_count", 0) for r in results)

        html_output = [
            "<html><head><title>API Test Report</title>",
            "<style>",
            "body{font-family:Arial;}table{width:100%;border-collapse:collapse;}",
            "th,td{border:1px solid #ccc;padding:6px;vertical-align:top;}",
            ".passed{color:green;font-weight:bold;}",
            ".failed{color:red;font-weight:bold;}",
            ".body{font-color:white;}",
            ".auth-info{background:#f0f7ff;padding:10px;border-radius:5px;margin-bottom:15px;}",
            ".contract-info{background:#fff3cd;padding:10px;border-radius:5px;margin-bottom:15px;border:1px solid #ffc107;}",
            ".schema-valid{color:#28a745;font-weight:bold;}",
            ".schema-invalid{color:#dc3545;font-weight:bold;}",
            ".schema-na{color:#6c757d;font-style:italic;}",
            ".violation-list{font-size:11px;margin:5px 0;padding-left:15px;}",
            ".violation-item{margin:3px 0;color:#dc3545;}",
            ".summary-box{display:inline-block;padding:8px 15px;margin:5px;border-radius:5px;font-weight:bold;}",
            ".summary-passed{background:#d4edda;color:#155724;}",
            ".summary-failed{background:#f8d7da;color:#721c24;}",
            ".summary-na{background:#e2e3e5;color:#383d41;}",
            "</style>",
            "</head><body id ='body'>",

            "<h2>🧪 API Test Execution Report</h2>",
            f"<p>Generated: {timestamp}</p>",
            f"<div class='auth-info'><strong>🔐 Authentication:</strong> {html.escape(auth_info)}</div>",
            
            "<div class='contract-info'>",
            "<strong>📋 Contract Testing Summary</strong><br>",
            f"<div class='summary-box summary-passed'>✅ Schema Valid: {schema_passed}</div>",
            f"<div class='summary-box summary-failed'>❌ Schema Violations: {schema_failed}</div>",
            f"<div class='summary-box summary-na'>⚪ No Schema: {schema_not_found}</div>",
            f"<div class='summary-box summary-failed' style='background:#fff;border:1px solid #dc3545;'>Total Violations: {total_violations}</div>",
            "</div>",
            
            f"<h3>Test Coverage: {coverage:.2f}%</h3>",

            "<table id='resultsTable'>",

            "<tr>"
            "<th>S.No</th>"
            "<th>Scenario</th>"
            "<th>Request Body</th>"
            "<th>Response</th>"
            "<th>Status Code</th>"
            "<th>HTTP Request</th>"
            "<th>Method</th>"
            "<th>Contract<br>Validation</th>"
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

        for idx, r in enumerate(results):
            scenario = r.get("scenario", "N/A")
            request_body = r.get("request_body", "N/A")

            status = r.get("response", r.get("error", "N/A"))
            status_code = r.get("status", "N/A")
            http_request = r.get("url", "N/A")
            method = r.get("method", "N/A")

            result_flag = r.get("result", "N/A")
            color = "green" if result_flag == "passed" else "red"
            
            schema_validation = r.get("schema_validation", {})
            schema_found = schema_validation.get("schema_found", False)
            schema_valid = schema_validation.get("schema_valid", True)
            violations = schema_validation.get("violations", [])
            
            if not schema_found:
                schema_cell = "<span class='schema-na'>No Schema</span>"
            elif schema_valid:
                schema_cell = "<span class='schema-valid'>✅ Valid</span>"
            else:
                # Show violations
                violation_html = f"<span class='schema-invalid'>❌ {len(violations)} Violation(s)</span>"
                violation_html += "<ul class='violation-list'>"
                for v in violations[:3]:  # Show max 3 violations
                    path = html.escape(v.get("path", ""))
                    msg = html.escape(v.get("message", "")[:50])
                    violation_html += f"<li class='violation-item'><code>{path}</code>: {msg}</li>"
                if len(violations) > 3:
                    violation_html += f"<li class='violation-item'><em>...+{len(violations) - 3} more</em></li>"
                violation_html += "</ul>"
                schema_cell = violation_html

            html_output.append(
                f"<tr>"
                f"<td>{idx + 1}</td>"
                f"<td>{html.escape(str(scenario))}</td>"
                f"<td><code>{html.escape(str(request_body))}</code></td>"
                f"<td>{html.escape(str(status)[:200])}</td>"
                f"<td>{status_code}</td>"
                f"<td><code>{html.escape(str(http_request))}</code></td>"
                f"<td>{method}</td>"
                f"<td>{schema_cell}</td>"
                f"<td style='font-weight:bold; color:{color}'>{result_flag.upper()}</td>"
                f"</tr>"
            )

        html_output.append("</table>")

        html_output.append("""
        <script>
        function filterResults() {
            let filter = document.getElementById('resultFilter').value;
            let table = document.getElementById('resultsTable');
            let rows = table.getElementsByTagName('tr');

            for (let i = 1; i < rows.length; i++) {
                let resultCell = rows[i].getElementsByTagName('td')[8];
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

        schema_failures = [r for r in results if r.get("schema_validation", {}).get("schema_found", False) 
                          and not r.get("schema_validation", {}).get("schema_valid", True)]
        
        if schema_failures:
            html_output.append("<h2>📋 Contract Violations (Schema Validation Failures)</h2>")
            html_output.append("<p style='color:#666;'>The following API responses did not match their OpenAPI schema definitions:</p>")
            
            for r in schema_failures:
                scenario = html.escape(str(r.get("scenario", "N/A")))
                endpoint = html.escape(str(r.get("url", "N/A")))
                method = r.get("method", "N/A")
                violations = r.get("schema_validation", {}).get("violations", [])
                
                html_output.append(
                    f"<div style='background:#fff5f5;border:1px solid #dc3545;border-radius:5px;padding:10px;margin:10px 0;'>"
                    f"<strong style='color:#dc3545;'>❌ {scenario}</strong><br>"
                    f"<code>{method} {endpoint}</code>"
                    f"<table style='width:100%;margin-top:10px;font-size:12px;'>"
                    f"<tr style='background:#f8d7da;'><th>Path</th><th>Error</th><th>Expected</th><th>Actual</th></tr>"
                )
                
                for v in violations:
                    path = html.escape(v.get("path", ""))
                    message = html.escape(v.get("message", "")[:80])
                    expected = html.escape(v.get("expected", "")[:40])
                    actual = html.escape(v.get("actual", "")[:40])
                    html_output.append(
                        f"<tr><td><code>{path}</code></td><td>{message}</td>"
                        f"<td>{expected}</td><td>{actual}</td></tr>"
                    )
                
                html_output.append("</table></div>")
        
        if uncovered:
            html_output.append("<h2>Uncovered Endpoints from OpenAPI Spec</h2><ul>")
            for ep in uncovered:
                html_output.append(f"<li>{html.escape(ep)}</li>")
            html_output.append("</ul>")
        
        html_output.append("</body></html>")

        full_html = "\n".join(html_output)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        return json.dumps({"execution_output": full_html})

    
    
    def __call__(self, state, batch_size: int = 5):
        try:
            self.auth_handler = AuthHandler(state.project_path)
            
            if self.auth_handler.is_authenticated():
                print(f"[TEST] Authentication: {self.auth_handler.get_auth_summary()}", file=sys.stderr, flush=True)
            else:
                print("[TEST] Running tests without authentication", file=sys.stderr, flush=True)
            
            openapi_dir = os.path.join(state.project_path, "output")
            filepath = self._find_latest_openapi_spec(openapi_dir)
            
            if not filepath:
                raise FileNotFoundError(f"OpenAPI spec not found in {openapi_dir}")
            
            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.endswith((".yaml", ".yml")):
                    state.analysis = yaml.safe_load(f)
                else:
                    state.analysis = json.load(f)
            
            self.schema_validator = SchemaValidator(state.analysis)
            print("[TEST] Schema Validator initialized for contract testing", file=sys.stderr, flush=True)

        
            cleaned_text = re.sub(r"^\s*Feature:.*$", "", state.feature_text, flags=re.MULTILINE)

            cleaned_text = re.sub(r"^\s*(?:@\w[\w-]*\s*)+", "", cleaned_text, flags=re.MULTILINE)

            cleaned_text = re.sub(r"^\s*#.*$", "", cleaned_text, flags=re.MULTILINE)

            cleaned_text = re.sub(r"\n{2,}", "\n", cleaned_text).strip()

            raw_scenarios = re.split(r"(?m)^\s*Scenario:\s*", cleaned_text)

            scenarios = []
            for chunk in raw_scenarios:
                chunk = chunk.strip()
                if not chunk:
                    continue

                lines = chunk.split("\n")
                scenario_name = lines[0].strip()

                scenario_body = "\n".join(lines[1:]).strip()

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

                try:
                    parsed = json.loads(content)
                except:
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
                    url = r.get("url", "")
                    method = r.get("method", "GET")
                    status_code = r.get("status", 0)
                    response_body = r.get("response", {})
                    
                    schema_result = self._validate_response_schema(
                        url=url,
                        method=method,
                        status_code=status_code,
                        response_body=response_body
                    )
                    
                    r["schema_validation"] = schema_result
                    
                    if schema_result.get("schema_found") and not schema_result.get("schema_valid"):
                        r["result"] = "failed"
                        r["schema_failure"] = True
                        print(
                            f"[SCHEMA] ❌ Contract violation in '{r.get('scenario', 'N/A')}': "
                            f"{schema_result.get('violation_count', 0)} violations",
                            file=sys.stderr, flush=True
                        )
                    elif schema_result.get("schema_found") and schema_result.get("schema_valid"):
                        print(
                            f"[SCHEMA] ✅ Schema valid for '{r.get('scenario', 'N/A')}'",
                            file=sys.stderr, flush=True
                        )

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