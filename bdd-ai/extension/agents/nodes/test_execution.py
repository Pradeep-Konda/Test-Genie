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
        
        # endpoint = self._extract_endpoint_path(url)
        
        try:
            result = self.schema_validator.validate_response(
                endpoint=url,
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
        

        # --- Calculate OpenAPI coverage ---
        coverage, uncovered = self._calculate_openapi_coverage(state.feature_text, state.analysis)

        # Save coverage info so XML report can reuse it
        self._last_coverage = coverage
        self._last_uncovered = uncovered

        self._generate_junit_xml_report(results, output_dir, timestamp)

        
        # --- Basic execution stats ---
        total_tests = len(results)
        passed_tests = sum(1 for r in results if str(r.get("result", "")).lower() == "passed")
        failed_tests = sum(1 for r in results if str(r.get("result", "")).lower() == "failed")
        pass_rate = (passed_tests / total_tests * 100) if total_tests else 0.0

        # --- Get authentication info ---
        auth_info = "No authentication"
        if self.auth_handler and self.auth_handler.is_authenticated():
            auth_info = self.auth_handler.get_auth_summary()

        html_output = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='UTF-8' />",
            f"<title>API Test Report - {timestamp}</title>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0' />",
            "<style>",
            ":root{",
            "  --tg-bg:#f9fafb;",
            "  --tg-surface:#ffffff;",
            "  --tg-surface-alt:#f3f4f6;",
            "  --tg-border-subtle:rgba(148,163,184,0.4);",
            "  --tg-text:#111827;",
            "  --tg-muted:#6b7280;",
            "  --tg-pass:#22c55e;",
            "  --tg-fail:#ef4444;",
            "  --tg-status-success:#22c55e;",
            "  --tg-status-client:#f97316;",
            "  --tg-status-server:#ef4444;",
            "}",
            "*,*::before,*::after{box-sizing:border-box;}",
            "body{margin:0;padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background-color:var(--tg-bg);color:var(--tg-text);-webkit-font-smoothing:antialiased;}",
            ".container{max-width:1200px;margin:0 auto;}",
            ".header{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:20px;}",
            ".header-main h1{margin:0 0 4px;font-size:26px;font-weight:600;}",
            ".header-main .subtitle{margin:0;font-size:14px;color:var(--tg-muted);}",
            ".header-main .timestamp{font-size:12px;color:var(--tg-muted);margin-top:4px;}",
            ".header-side{text-align:right;font-size:12px;color:var(--tg-muted);}",
            ".badge{display:inline-flex;align-items:center;justify-content:center;padding:2px 10px;border-radius:999px;border:1px solid var(--tg-border-subtle);font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;}",
            ".summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px;}",
            ".card{border-radius:12px;padding:12px 14px;border:1px solid var(--tg-border-subtle);background-color:var(--tg-surface);}",
            ".card-title{font-size:11px;text-transform:uppercase;letter-spacing:0.14em;color:var(--tg-muted);margin-bottom:4px;}",
            ".metric-main{display:flex;align-items:flex-end;gap:6px;margin-bottom:4px;}",
            ".metric-value{font-size:24px;font-weight:600;}",
            ".metric-unit{font-size:12px;color:var(--tg-muted);}",
            ".metric-sub{font-size:12px;color:var(--tg-muted);}",
            ".metric-pass{color:var(--tg-pass);}",
            ".metric-fail{color:var(--tg-fail);}",
            ".coverage-bar{margin-top:6px;height:6px;border-radius:999px;border:1px solid rgba(148,163,184,0.55);background-color:var(--tg-surface-alt);overflow:hidden;}",
            ".coverage-bar-inner{height:100%;background-image:linear-gradient(90deg,#22c55e,#14b8a6);}",
            ".toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin:10px 0 16px;}",
            ".toolbar-left{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;color:var(--tg-muted);}",
            ".toolbar-right{display:flex;flex-wrap:wrap;gap:8px;align-items:center;}",
            ".filter-label{font-size:12px;color:var(--tg-muted);margin-right:4px;}",
            ".filter-select,.filter-input{font-size:12px;padding:6px 10px;border-radius:999px;border:1px solid var(--tg-border-subtle);background-color:var(--tg-surface);color:var(--tg-text);min-width:120px;}",
            ".filter-input{min-width:230px;}",
            "table{width:100%;border-collapse:collapse;font-size:14px;border-radius:12px;overflow:hidden;}",
            "thead{background-color:var(--tg-surface-alt);border-bottom:1px solid var(--tg-border-subtle);}",
            "th,td{padding:8px 10px;text-align:left;border-bottom:1px solid rgba(148,163,184,0.25);vertical-align:top;}",
            "th{font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--tg-muted);white-space:nowrap;}",
            "tbody tr:nth-child(even){background-color:var(--tg-surface-alt);}",
            "tbody tr:hover{background-color:#e5e7eb33;}",
            ".col-scenario{min-width:220px;}",
            ".col-request{min-width:180px;}",
            ".col-response{min-width:260px;}",
            ".col-url{min-width:200px;}",
            ".scenario-name{font-weight:500;margin-bottom:2px;}",
            ".code-block{font-family:ui-monospace,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;font-size:13px;white-space:pre-wrap;word-break:break-word;}",
            ".status-pill{display:inline-flex;align-items:center;justify-content:center;padding:2px 8px;border-radius:999px;border:1px solid transparent;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;}",
            ".status-success{border-color:var(--tg-status-success);box-shadow:0 0 0 1px rgba(34,197,94,0.35);}",
            ".status-client{border-color:var(--tg-status-client);box-shadow:0 0 0 1px rgba(249,115,22,0.35);}",
            ".status-server{border-color:var(--tg-status-server);box-shadow:0 0 0 1px rgba(239,68,68,0.35);}",
            ".status-unknown{border-color:var(--tg-border-subtle);}",
            ".result-badge{display:inline-flex;align-items:center;justify-content:center;padding:2px 10px;border-radius:999px;border:1px solid transparent;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;}",
            ".result-passed{border-color:var(--tg-pass);box-shadow:0 0 0 1px rgba(34,197,94,0.4);}",
            ".result-failed{border-color:var(--tg-fail);box-shadow:0 0 0 1px rgba(239,68,68,0.4);}",
            ".table-wrapper{border-radius:12px;border:1px solid var(--tg-border-subtle);background-color:var(--tg-surface);overflow-x: auto;overflow-y: auto;max-width: 100%;}",
            ".empty-state{margin-top:16px;font-size:13px;color:var(--tg-muted);}",
            ".uncovered{margin-top:20px;font-size:13px;}",
            ".uncovered h2{font-size:14px;margin-bottom:8px;}",
            ".uncovered ul{margin:0;padding-left:18px;}",
            ".uncovered li{margin:2px 0;}",
            ".footer-note{margin-top:14px;font-size:11px;color:var(--tg-muted);}",
            "@media (max-width:768px){body{padding:16px;}th:nth-child(1),td:nth-child(1){display:none;}}",
            "</style>",
            "</head>",
            "<body>",
            "<div class='container'>",
            "<header class='header'>",
            "<div class='header-main'>",
            "<h1>API Test Execution Report</h1>",
            "<p class='subtitle'>Execution results generated by Test-Genie</p>",
            f"<p class='timestamp'>Generated at {timestamp}</p>",
            "</div>",
            "<div class='header-side'>",
            "<div class='badge'>Execution Summary</div>",
            f"<div style='margin-top:6px;'>Authentication: {html.escape(auth_info)}</div>",
            "</div>",
            "</header>",
        ]

        html_output.extend(
            [
                "<section class='summary-grid'>",
                "<div class='card'>",
                "<div class='card-title'>Total Scenarios</div>",
                "<div class='metric-main'>",
                f"<div class='metric-value'>{total_tests}</div>",
                "</div>",
                "<div class='metric-sub'>All executed scenarios</div>",
                "</div>",
                "<div class='card'>",
                "<div class='card-title'>Pass / Fail</div>",
                "<div class='metric-main'>",
                f"<div class='metric-value metric-pass'>{passed_tests}</div>",
                f"<div class='metric-unit'>passed</div>",
                "</div>",
                f"<div class='metric-sub'><span class='metric-fail'>{failed_tests}</span> failed</div>",
                "</div>",
                "<div class='card'>",
                "<div class='card-title'>Pass Rate</div>",
                "<div class='metric-main'>",
                f"<div class='metric-value'>{pass_rate:.1f}</div>",
                "<div class='metric-unit'>%</div>",
                "</div>",
                f"<div class='metric-sub'>Based on {total_tests} scenarios</div>",
                "</div>",
                "<div class='card'>",
                "<div class='card-title'>OpenAPI Coverage</div>",
                "<div class='metric-main'>",
                f"<div class='metric-value'>{coverage:.1f}</div>",
                "<div class='metric-unit'>%</div>",
                "</div>",
                "<div class='coverage-bar'>",
                f"<div class='coverage-bar-inner' style='width:{coverage:.1f}%;'></div>",
                "</div>",
                "<div class='metric-sub'>Endpoints and methods covered by tests</div>",
                "</div>",
                "</section>",
            ]
        )

        # Toolbar (filters)
        html_output.extend(
            [
                "<section class='toolbar'>",
                "<div class='toolbar-left'>",
                f"<span>Showing {total_tests} scenario{'s' if total_tests != 1 else ''}</span>",
                "</div>",
                "<div class='toolbar-right'>",
                "<label class='filter-label' for='resultFilter'>Result</label>",
                "<select id='resultFilter' class='filter-select' onchange='filterResults()'>",
                "<option value='all'>All</option>",
                "<option value='passed'>Passed</option>",
                "<option value='failed'>Failed</option>",
                "</select>",
                "<label class='filter-label' for='searchInput'>Search</label>",
                "<input id='searchInput' class='filter-input' type='text' placeholder='Filter by scenario, method, or URL' oninput='filterResults()' />",
                "</div>",
                "</section>",
            ]
        )

        if results:
            html_output.append("<div class='table-wrapper'>")
            html_output.append("<table id='resultsTable'>")
            html_output.append(
                "<thead><tr>"
                "<th>#</th>"
                "<th class='col-scenario'>Scenario</th>"
                "<th class='col-request'>Request Body</th>"
                "<th class='col-response'>Response</th>"
                "<th>Status</th>"
                "<th class='col-url'>HTTP Request</th>"
                "<th>Method</th>"
                "<th>Contract<br>Validation</th>"
                "<th>Result</th>"
                "</tr></thead><tbody>"
            )

            for idx, r in enumerate(results):
                scenario = html.escape(str(r.get("scenario", "N/A")))
                request_body_raw = r.get("request_body", "N/A")
                request_body = html.escape(str(request_body_raw)) if request_body_raw is not None else "N/A"
                response_value = r.get("response", r.get("error", "N/A"))
                response_text = html.escape(str(response_value))
                status_code = r.get("status", "N/A")
                http_request = html.escape(str(r.get("url", "N/A")))
                method = html.escape(str(r.get("method", "N/A")))

                schema_validation = r.get("schema_validation", {})
                schema_found = schema_validation.get("schema_found", False)
                schema_valid = schema_validation.get("schema_valid", True)
                violations = schema_validation.get("violations", [])
                
                if not schema_found:
                    schema_cell = "<span class='result-badge result-failed'>No Schema</span>"
                elif schema_valid:
                    schema_cell = "<span class='result-badge result-passed'>Valid</span>"
                else:
                    # Show violations
                    violation_html = f"<span class='schema-invalid'>{len(violations)} Violation(s)</span>"
                    violation_html += "<ul class='violation-list'>"
                    for v in violations[:3]:  # Show max 3 violations
                        path = html.escape(v.get("path", ""))
                        msg = html.escape(v.get("message", "")[:100])
                        violation_html += f"<li class='violation-item'><code>{path}</code>: {msg}</li>"
                    if len(violations) > 3:
                        violation_html += f"<li class='violation-item'><em>...+{len(violations) - 3} more</em></li>"
                    violation_html += "</ul>"
                    schema_cell = violation_html

                # Status classification
                status_class = "status-unknown"
                try:
                    code_int = int(status_code)
                    if 200 <= code_int < 300:
                        status_class = "status-success"
                    elif 400 <= code_int < 500:
                        status_class = "status-client"
                    elif 500 <= code_int < 600:
                        status_class = "status-server"
                except Exception:
                    pass

                result_flag = str(r.get("result", "N/A")).lower()
                if result_flag == "passed":
                    result_class = "result-badge result-passed"
                    result_label = "PASSED"
                elif result_flag == "failed":
                    result_class = "result-badge result-failed"
                    result_label = "FAILED"
                else:
                    result_class = "result-badge"
                    result_label = html.escape(str(r.get("result", "N/A"))).upper()

                html_output.append(
                    "<tr>"
                    f"<td>{idx + 1}</td>"
                    f"<td><div class='scenario-name'>{scenario}</div></td>"
                    f"<td><div class='code-block'>{request_body}</div></td>"
                    f"<td><div class='code-block'>{response_text}</div></td>"
                    f"<td><span class='status-pill {status_class}'>{html.escape(str(status_code))}</span></td>"
                    f"<td><div class='code-block'>{http_request}</div></td>"
                    f"<td>{method}</td>"
                    f"<td>{schema_cell}</td>"
                    f"<td><span class='{result_class}'>{result_label}</span></td>"
                    "</tr>"
                )

            html_output.append("</tbody></table></div>")
        else:
            html_output.append("<p class='empty-state'>No test results were produced.</p>")

        # Uncovered endpoints section
        if uncovered:
            html_output.append("<section class='uncovered'>")
            html_output.append("<h2>Uncovered endpoints from OpenAPI spec</h2><ul>")
            for ep in uncovered:
                html_output.append(f"<li>{html.escape(str(ep))}</li>")
            html_output.append("</ul></section>")

        # Footer note
        html_output.append(
            "<p class='footer-note'>"
            "HTML and JUnit XML reports are saved under the "
            "<code>test_reports</code> folder in your project."
            "</p>"
        )

        # Filtering logic (by result + search)
        html_output.append(
            """
    <script>
function filterResults() {
    var filter = document.getElementById('resultFilter').value;
    var searchInput = document.getElementById('searchInput');
    var search = searchInput ? searchInput.value.toLowerCase() : "";
    var table = document.getElementById('resultsTable');
    if (!table) return;

    var rows = table.getElementsByTagName('tr');

    for (var i = 1; i < rows.length; i++) {
        var cells = rows[i].getElementsByTagName('td');
        if (!cells || cells.length === 0) continue;

        var resultCell = cells[8];
        var scenarioCell = cells[1];
        var urlCell = cells[5];
        var methodCell = cells[6];
        var contractCell = cells[7];

        // ----- RESULT MATCHING (FIXED) -----
        var isPassed = resultCell.querySelector('.result-passed') !== null;
        var isFailed = resultCell.querySelector('.result-failed') !== null;

        var matchesResult =
            filter === "all" ||
            (filter === "passed" && isPassed) ||
            (filter === "failed" && isFailed);

        // ----- SEARCH MATCHING -----
        var haystack = "";
        if (scenarioCell) haystack += scenarioCell.textContent.toLowerCase() + " ";
        if (urlCell) haystack += urlCell.textContent.toLowerCase() + " ";
        if (methodCell) haystack += methodCell.textContent.toLowerCase() + " ";
        if (contractCell) haystack += contractCell.textContent.toLowerCase();

        var matchesSearch = (!search || haystack.indexOf(search) !== -1);

        rows[i].style.display = (matchesResult && matchesSearch) ? "" : "none";
    }
}
</script>

    """
        )

        html_output.append("</div></body></html>")

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

            # Global execution metadata for CI
            coverage = getattr(self, "_last_coverage", None)
            uncovered = getattr(self, "_last_uncovered", [])

            auth_info = "No authentication"
            if self.auth_handler and self.auth_handler.is_authenticated():
                auth_info = self.auth_handler.get_auth_summary()

            suite_out = ET.SubElement(testsuite, "system-out")

            suite_out.text = (
                f"\nAuthentication: {auth_info}\n"
                f"OpenAPI Coverage: {coverage if coverage is not None else 'N/A'}%"
            )


            
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
            
            # Uncovered endpoints summary (END)
            end_out = ET.SubElement(testsuite, "system-out")
            end_out.text = (
                "\nUncovered Endpoints:\n" +
                ("\n".join(f"- {ep}" for ep in uncovered) if uncovered else "- None")
)

            
            
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
    def __call__(self, state, batch_size: int = 10):
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

            self.schema_validator = SchemaValidator(state.analysis)

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