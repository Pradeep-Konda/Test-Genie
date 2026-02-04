import os
import re
import sys
import json
import requests
import traceback
import yaml
from datetime import datetime
from urllib.parse import quote
from typing import List, Optional, Any, Dict
from utils.auth_handler import AuthHandler
from utils.schema_validator import SchemaValidator
from utils.report_handler import ReportHandler
import utils.common as common


class TestExecutionNode:

    def __init__(self, features_dir: str = "bdd_tests"):
        self.features_dir = features_dir

        # Auth handler initialized during execution
        self.auth_handler: Optional[AuthHandler] = None

        # OpenAPI schema validator (contract testing)
        self.schema_validator: Optional[SchemaValidator] = None

        # Used to persist auth headers across calls
        self._auth_headers = {}

        # Content type mapping for file uploads
        self.content_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".yaml": "application/x-yaml",
            ".yml": "application/x-yaml",
            ".csv": "text/csv",
            ".json": "application/json",
            ".xls": "application/vnd.ms-excel",
            ".svg": "image/svg+xml",
            ".xml": "application/xml",
        }

    # --------------------------------------------------------
    # AUTH STATUS
    # --------------------------------------------------------
    def _log_auth_status(self, project_path):
        try:
            self.auth_handler = AuthHandler(project_path)
            if self.auth_handler.is_authenticated():
                print(
                    f"[TEST] Authentication: {self.auth_handler.get_auth_summary()}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    "[TEST] Running tests without authentication",
                    file=sys.stderr,
                    flush=True,
                )
        except Exception:
            pass

    # --------------------------------------------------------
    # URL BUILDING
    # --------------------------------------------------------
    def _build_url(self, method, url, base_url):
        try:
            final_url = url if url.startswith("http") else f"{base_url.rstrip('/')}/{url.lstrip('/')}"

            if not self.auth_handler:
                return final_url

            headers = self.auth_handler.get_auth_headers()
            self._auth_headers = headers

            auth_params = self.auth_handler.get_auth_query_params()
            if not auth_params:
                return final_url

            separator = "&" if "?" in final_url else "?"
            query = "&".join(
                f"{k}={quote(str(v), safe='')}" for k, v in auth_params.items()
            )

            return f"{final_url}{separator}{query}"
        except Exception:
            return url

    # --------------------------------------------------------
    # RESPONSE PARSING
    # --------------------------------------------------------
    def _parse_response(self, response):
        status_code = response.status_code
        raw = response.text

        try:
            return response.json(), status_code
        except Exception:
            lowered = raw.lower()
            if "<!doctype html>" in lowered or "<html" in lowered:
                raw = f"HTTP {status_code} Error"
            return raw, status_code

    # --------------------------------------------------------
    # JSON BODY SAFE PARSER
    # --------------------------------------------------------
    def _get_json_body(self, body):
        try:
            return json.loads(body)
        except Exception:
            return body

    # --------------------------------------------------------
    # FILE CONTENT TYPE
    # --------------------------------------------------------
    def _get_content_type(self, filename):
        try:
            if not filename:
                raise ValueError("File name is empty")
            name = filename.lower()
            ext = name[name.rfind("."):] if "." in name else ""
            return self.content_type_map.get(ext, "application/octet-stream")
        except Exception:
            return "application/octet-stream"

    # --------------------------------------------------------
    # MULTIPART FORM HANDLING
    # --------------------------------------------------------
    async def _prepare_request_for_form_data(
        self, key, value, resources, files, file_flag
    ):
        try:
            if resources:
                for item in resources:
                    if item.filename == value:
                        buffer = await item.read()
                        content_type = self._get_content_type(item.filename)
                        files.append(
                            (key, (item.filename, buffer, content_type))
                        )
                        file_flag = True
                        break
            return files, file_flag
        except Exception:
            raise

    async def _prepare_payload(self, content, body, headers, resources):
        files = []
        data = {}
        json_body = None

        try:
            json_body = self._get_json_body(body)

            if content and content.get("multipart/form-data"):
                file_flag = False
                for key, value in json_body.items():
                    files, file_flag = await self._prepare_request_for_form_data(
                        key, value, resources, files, file_flag
                    )
                    if not file_flag:
                        data.update({key: str(value)})

                return data, files, None, headers

            headers.update({"Content-Type": "application/json"})
            return None, None, json_body, headers

        except Exception:
            return data, files, json_body, headers

    # --------------------------------------------------------
    # HTTP EXECUTOR
    # --------------------------------------------------------
    async def _run_curl_command(
        self,
        method: str,
        url: str,
        base_url: str,
        resources,
        content,
        body: Optional[str] = None,
    ):
        try:
            files = []
            data = {}
            headers = {}
            response = None
            status_code = 0

            method = method.upper()
            final_url = self._build_url(method, url, base_url)

            headers.update(self._auth_headers)

            data, files, json_body, headers = await self._prepare_payload(
                content, body, headers, resources
            )

            response = requests.request(
                method=method,
                url=final_url,
                json=json_body if isinstance(json_body, dict) else None,
                data=data,
                files=files,
                headers=headers,
                timeout=10,
            )

            result, status_code = self._parse_response(response)

            return {
                "url": final_url,
                "method": method,
                "status": status_code,
                "response": result,
                "stderr": None,
            }

        except Exception as e:
            return {
                "error": str(e),
                "url": final_url,
                "method": method,
                "status": status_code,
                "stderr": str(e),
            }

    # --------------------------------------------------------
    # OPENAPI SCHEMA VALIDATION
    # --------------------------------------------------------
    def _validate_response_schema(
        self,
        url: str,
        method: str,
        status_code: int,
        response_body: Any,
    ) -> Dict[str, Any]:

        if not self.schema_validator:
            return {
                "schema_valid": True,
                "schema_found": False,
                "violations": [],
                "violation_count": 0,
            }

        try:
            result = self.schema_validator.validate_response(
                endpoint=url,
                method=method,
                status_code=status_code,
                response_body=response_body,
            )

            return {
                "schema_valid": result.is_valid,
                "schema_found": result.schema_found,
                "violations": [v.to_dict() for v in result.violations],
                "violation_count": len(result.violations),
            }

        except Exception as e:
            print(f"[SCHEMA] Validation error: {e}", file=sys.stderr)
            return {
                "schema_valid": True,
                "schema_found": False,
                "violations": [],
                "violation_count": 0,
                "error": str(e),
            }

    # --------------------------------------------------------
    # FEATURE FILE PREPROCESSING
    # --------------------------------------------------------
    def _preprocess_feature_text(self, feature_text):
        try:
            cleaned_text = re.sub(r"^\s*Feature:.*$", "", feature_text, flags=re.MULTILINE)
            cleaned_text = re.sub(r"^\s*#.*$", "", cleaned_text, flags=re.MULTILINE)
            cleaned_text = re.sub(r"\n{2,}", "\n", cleaned_text)
            return cleaned_text.strip()
        except Exception as e:
            raise RuntimeError("Failed in _preprocess_feature_text()", e)
        
    # --------------------------------------------------------
    # Finding Spec file
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # SCENARIO PARSER
    # --------------------------------------------------------
    def _parse_scenarios(self, cleaned_text):
        try:
            scenarios = []
            current_tags = set()
            current_lines = []
            scenario_name = None

            for line in cleaned_text.splitlines():
                line = line.rstrip()

                if line.strip().startswith("@"):
                    current_tags.add(line.strip().lower())
                    continue

                if line.strip().startswith("Scenario:"):
                    if current_lines:
                        scenarios.append({
                            "name": scenario_name,
                            "text": "\n".join(current_lines),
                            "tags": set(current_tags),
                        })
                        current_lines = []
                        current_tags = set()

                    scenario_name = line.replace("Scenario:", "").strip()
                    current_lines.append(line)
                    continue

                if current_lines:
                    current_lines.append(line)

            if current_lines:
                scenarios.append({
                    "name": scenario_name,
                    "text": "\n".join(current_lines),
                    "tags": set(current_tags),
                })

            return scenarios

        except Exception as e:
            raise ValueError("Error Feature text parsing : Test Execution", e)

    # --------------------------------------------------------
    # SCENARIO EXECUTION
    # --------------------------------------------------------
    async def _execute_scenario(self, scenario, state, resources, base_url):
        scenario_name = scenario["name"]
        full_scenario = scenario["text"]
        tags = scenario["tags"]
        is_negative = "@negative" in tags

        try:
            method, url, body = common._extract_http_call(full_scenario)
            expectations = common._extract_expected_status(full_scenario)
            content = common._get_content_from_spec(
                state.analysis, url, method, full_scenario
            )

            response = await self._run_curl_command(
                method=method,
                url=url,
                base_url=base_url,
                resources=resources,
                content=content,
                body=body,
            )

            status = response.get("status", 0)
            response_body = response.get("response", response.get("error"))

            status_passed = common._validate_status(
                actual_status=status,
                expectations=expectations,
                is_negative=is_negative,
            )

            schema_result = self._validate_response_schema(
                url=response["url"],
                method=method,
                status_code=status,
                response_body=response_body,
            )

            schema_passed = not (
                schema_result.get("schema_found")
                and not schema_result.get("schema_valid")
            )

            final_passed = status_passed and schema_passed

            return {
                "scenario": scenario_name,
                "request_body": body,
                "url": url,
                "method": method,
                "status": status,
                "response": response_body,
                "schema_validation": schema_result,
                "result": "passed" if final_passed else "failed",
            }

        except Exception as e:
            return {
                "scenario": scenario_name,
                "request_body": body,
                "url": url,
                "method": method,
                "status": status,
                "response": str(e),
                "result": "failed",
            }

    # --------------------------------------------------------
    # CORE EXECUTION ENTRY
    # --------------------------------------------------------
    async def __call__(self, state, resources=None):
        try:
            self._log_auth_status(state.project_path)

            self.report_handler = ReportHandler(self.auth_handler)

            openapi_dir = os.path.join(state.project_path, "output")

            filepath = self._find_latest_openapi_spec(openapi_dir)

            with open(filepath, "r", encoding="utf-8") as f:
                if filepath.endswith((".yaml", ".yml")):
                    state.analysis = yaml.safe_load(f)
                else:
                    state.analysis = json.load(f)

            self.schema_validator = SchemaValidator(state.analysis)

            base_url = common._get_base_url_from_spec(state.analysis)

            cleaned_text = self._preprocess_feature_text(state.feature_text)
            scenarios = self._parse_scenarios(cleaned_text)

            results = []
            for scenario in scenarios:
                result = await self._execute_scenario(
                    scenario, state, resources, base_url
                )
                results.append(result)

            final_input = {
                "results": results,
                "curl_commands": [],
            }

            report_json = self.report_handler.generate_html_report(state, final_input)
            state.html_report = json.loads(report_json).get("html_report")
            state.xml_report = json.loads(report_json).get("xml_report")
            state.execution_output = state.html_report

            return state

        except Exception as e:
            traceback.print_exc()
            raise RuntimeError("Error in test execution") from e
