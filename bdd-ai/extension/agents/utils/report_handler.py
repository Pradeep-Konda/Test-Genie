from typing import List, Optional, Any, Dict
import html
import xml.etree.ElementTree as ET
import utils.common as common
import sys
import json
import os
from datetime import datetime
import traceback
from utils.auth_handler import AuthHandler

class ReportHandler:

    def __init__(self, auth_handler: AuthHandler):
        self.auth_handler = auth_handler

    async def _generate_junit_xml_report(self, results: List[Dict], output_dir: str, timestamp: str) -> Optional[str]:
        """
        Generates a JUnit XML report for CI/CD integration.

        Args:
            results: List of test result dictionaries

        Returns:
            Path to the generated XML file, or None if generation failed
        """
        try:
            total_tests = len(results)
            failures = sum(
                1 for r in results if r.get("result", "").lower() == "failed"
            )

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
            if self.auth_handler and await self.auth_handler.is_authenticated():
                auth_info = await self.auth_handler.get_auth_summary()


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
                testcase.set("time", "0")

                if result_flag == "failed":
                    failure = ET.SubElement(testcase, "failure")
                    failure.set(
                        "message",
                        f"API call failed: {method} {url} returned {status_code}",
                    )
                    failure.set("type", "AssertionError")

                    failure_details = [
                        f"Scenario: {scenario}",
                        f"Method: {method}",
                        f"URL: {url}",
                        f"Status Code: {status_code}",
                        f"Request Body: {request_body}",
                        f"Response: {str(response)[:500]}",
                    ]
                    failure.text = "\n".join(failure_details)

                system_out = ET.SubElement(testcase, "system-out")
                system_out.text = (
                    f"Request: {method} {url}\n"
                    f"Status: {status_code}\n"
                    f"Response: {str(response)[:1000]}"
                )

            # Uncovered endpoints summary (END)
            end_out = ET.SubElement(testsuite, "system-out")
            end_out.text = "Uncovered Endpoints:\n" + (
                "\n".join(f"- {ep}" for ep in uncovered) if uncovered else "- None"
            )

            xml_string = ET.tostring(testsuites, encoding="unicode", method="xml")
            xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string

            xml_path = os.path.join(output_dir, f"api_test_report_{timestamp}.xml")
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
            return xml_content

        except Exception as e:
            traceback.print_exc()
            print(
                f"[TEST] Warning: Failed to generate JUnit XML report: {e}",
                file=sys.stderr,
                flush=True,
            )
            return None

    async def _get_schema_cell_for_html(self, schema_found, schema_valid, violations):
        try:
            if not schema_found:
                schema_cell = (
                    "<span class='result-badge result-failed'>No Schemas</span>"
                )
            elif schema_valid:
                schema_cell = "<span class='result-badge result-passed'>Valid</span>"
            else:
                violation_html = f"<span class='schema-invalid'>{len(violations)} Violation(s)</span>"
                violation_html += "<ul class='violation-list'>"
                for v in violations[:3]:
                    path = html.escape(v.get("path", ""))
                    msg = html.escape(v.get("message", "")[:100])
                    violation_html += (
                        f"<li class='violation-item'><code>{path}</code>: {msg}</li>"
                    )
                if len(violations) > 3:
                    violation_html += f"<li class='violation-item'><em>...+{len(violations) - 3} more</em></li>"
                violation_html += "</ul>"
                schema_cell = violation_html
            return schema_cell
        except Exception:
            raise

    async def _get_status_class_for_html(self, status_code):
        status_class = "status-unknown"
        try:
            code_int = int(status_code)
            if 200 <= code_int < 300:
                status_class = "status-success"
            elif 400 <= code_int < 500:
                status_class = "status-client"
            elif 500 <= code_int < 600:
                status_class = "status-server"
            return status_class
        except Exception:
            pass

    async def _get_result_attributes(self, r):
        try:
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
            return result_class, result_label
        except Exception:
            raise

    async def _get_responses_for_html(self, idx, r):
        try:
            scenario = html.escape(str(r.get("scenario", "N/A")))
            request_body_raw = r.get("request_body", "N/A")
            request_body = (
                html.escape(str(request_body_raw))
                if request_body_raw is not None
                else "N/A"
            )
            response_value = r.get("response", r.get("error", "N/A"))
            response_text = html.escape(str(response_value))
            status_code = r.get("status", "N/A")
            http_request = html.escape(str(r.get("url", "N/A")))
            method = html.escape(str(r.get("method", "N/A")))

            schema_validation = r.get("schema_validation", {})
            schema_found = schema_validation.get("schema_found", False)
            schema_valid = schema_validation.get("schema_valid", True)
            violations = schema_validation.get("violations", [])

            schema_cell = await self._get_schema_cell_for_html(
                schema_found, schema_valid, violations
            )
            status_class = await self._get_status_class_for_html(status_code)
            result_class, result_label = await self._get_result_attributes(r)

            return (
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
        except Exception:
            raise

    async def generate_html_report(self, state, data):
        """Generates HTML report + returns the HTML content (VS Code receives it)."""

        results = data.get("results", [])
        div_class_metric_main = "<div class='metric-main'>"
        div_class_card = "<div class='card'>"
        div_close = "</div>"

        # --- Calculate OpenAPI coverage ---
        coverage, uncovered = await common._calculate_openapi_coverage(
            state.feature_text, state.analysis
        )

        # Save coverage info so XML report can reuse it
        self._last_coverage = coverage
        self._last_uncovered = uncovered


        output_dir = os.path.join(state.project_path, "test_reports")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = os.path.join(output_dir, f"api_test_report_{timestamp}.html")

        full_xml = await self._generate_junit_xml_report(results, output_dir, timestamp)

        # --- Basic execution stats ---
        total_tests = len(results)
        passed_tests = sum(
            1 for r in results if str(r.get("result", "")).lower() == "passed"
        )
        failed_tests = sum(
            1 for r in results if str(r.get("result", "")).lower() == "failed"
        )
        pass_rate = (passed_tests / total_tests * 100) if total_tests else 0

        # --- Get authentication info ---
        auth_info = "No authentication"
        if self.auth_handler and await self.auth_handler.is_authenticated():
            auth_info = await self.auth_handler.get_auth_summary()

        html_output = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='UTF-8' />",
            "<title>API Test Report</title>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0' />",
            "<style>",
            ":root{--tg-bg:#f9fafb;--tg-surface:#ffffff;--tg-surface-alt:#f3f4f6;"
            "--tg-border-subtle:rgba(148,163,184,0.4);--tg-text:#111827;"
            "--tg-muted:#6b7280;--tg-pass:#22c55e;--tg-fail:#ef4444;"
            "--tg-status-success:#22c55e;--tg-status-client:#f97316;"
            "--tg-status-server:#ef4444;}",
            "*,:before,:after{box-sizing:border-box;}",
            "body{margin:0;padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;"
            "background-color:var(--tg-bg);color:var(--tg-text);}",
            ".container{max-width:1200px;margin:0 auto;}",
            ".header{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:20px;}",
            ".header-main h1{margin:0 4px;font-size:26px;font-weight:600;}",
            ".header-main .subtitle{margin:0;font-size:14px;color:var(--tg-muted);}",
            ".header-main .timestamp{font-size:12px;color:var(--tg-muted);margin-top:4px;}",
            ".badge{display:inline-flex;align-items:center;justify-content:center;padding:2px 10px;border-radius:999px;"
            "border:1px solid var(--tg-border-subtle);font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;}",
            ".summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px;}",
            ".card{border-radius:12px;padding:12px 14px;border:1px solid var(--tg-border-subtle);background-color:var(--tg-surface);}",
            ".card-title{font-size:11px;text-transform:uppercase;letter-spacing:0.14em;color:var(--tg-muted);margin-bottom:4px;}",
            ".metric-main{display:flex;align-items:flex-end;gap:6px;margin-bottom:4px;}",
            ".metric-value{font-size:24px;font-weight:600;}",
            ".metric-unit{font-size:12px;color:var(--tg-muted);}",
            ".metric-sub{font-size:12px;color:var(--tg-muted);}",
            ".metric-pass{color:var(--tg-pass);}",
            ".metric-fail{color:var(--tg-fail);}",
            ".coverage-bar{margin-top:6px;height:6px;border-radius:999px;border:1px solid rgba(148,163,184,0.55);"
            "background-color:var(--tg-surface-alt);overflow:hidden;}",
            ".coverage-bar-inner{height:100%;background-image:linear-gradient(90deg,#22c55e,#14b8a6);}",
            ".toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;margin:10px 0 16px;}",
            ".toolbar-left{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;color:var(--tg-muted);}",
            ".toolbar-right{display:flex;flex-wrap:wrap;gap:8px;align-items:center;}",
            ".filter-label{font-size:12px;color:var(--tg-muted);margin-right:4px;}",
            ".filter-select,.filter-input{font-size:12px;padding:6px 10px;border-radius:999px;border:1px solid var(--tg-border-subtle);"
            "background-color:var(--tg-surface);color:var(--tg-text);}",
            ".filter-input{min-width:230px;}",
            "table{width:100%;border-collapse:collapse;font-size:14px;border-radius:12px;overflow:hidden;}",
            "thead{background-color:var(--tg-surface-alt);border-bottom:1px solid var(--tg-border-subtle);}",
            "th,td{padding:8px 10px;text-align:left;border-bottom:1px solid rgba(148,163,184,0.25);vertical-align:top;}",
            "th{font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--tg-muted);white-space:nowrap;}",
            "tbody tr:nth-child(even){background-color:var(--tg-surface-alt);}",
            "tbody tr:hover{background-color:#e5e7eb;}",
            ".code-block{font-family:ui-monospace,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;"
            "font-size:13px;white-space:pre-wrap;word-break:break-word;}",
            ".status-pill{display:inline-flex;align-items:center;justify-content:center;padding:2px 8px;border-radius:999px;"
            "border:1px solid transparent;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;}",
            ".status-success{border-color:var(--tg-status-success);box-shadow:0 0 0 1px rgba(34,197,94,0.4);}",
            ".status-client{border-color:var(--tg-status-client);box-shadow:0 0 0 1px rgba(249,115,22,0.35);}",
            ".status-server{border-color:var(--tg-status-server);box-shadow:0 0 0 1px rgba(239,68,68,0.35);}",
            ".status-unknown{border-color:var(--tg-border-subtle);}",
            ".result-badge{display:inline-flex;align-items:center;justify-content:center;padding:2px 10px;border-radius:999px;"
            "border:1px solid transparent;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;}",
            ".result-passed{border-color:var(--tg-pass);box-shadow:0 0 0 1px rgba(34,197,94,0.4);}",
            ".result-failed{border-color:var(--tg-fail);box-shadow:0 0 0 1px rgba(239,68,68,0.4);}",
            "@media (max-width:768px){body{padding:16px;}th:nth-child(1),td:nth-child(1){display:none;}}",
            "</style>",
            "</head>",
            "<body>",
            "<div class='container'>",
            "</head>",
            "<body>",
            "<div class='container'>",
            "<header class='header'>",
            "<div class='header-main'>",
            "<h1>API Test Execution Report</h1>",
            "<p class='subtitle'>Execution results generated by Test-Genie</p>",
            div_close,
            "<div class='header-side'>",
            "<div class='badge'>Execution Summary</div>",
            f"<div style='margin-top:6px;'>Authentication: {html.escape(auth_info)}</div>",
            "</div>",
            "</header>",
        ]

        html_output.extend(
            [
                "<section class='summary-grid'>",
                div_class_card,
                "<div class='card-title'>Total Scenarios</div>",
                div_class_metric_main,
                f"<div class='metric-value'>{total_tests}</div>",
                div_close,
                "<div class='metric-sub'>All executed scenarios</div>",
                div_close,
                div_class_card,
                "<div class='card-title'>Pass / Fail</div>",
                div_class_metric_main,
                f"<div class='metric-value metric-pass'>{passed_tests}</div>",
                "<div class='metric-unit'>passed</div>",
                div_close,
                f"<div class='metric-sub'><span class='metric-fail'>{failed_tests}</span> failed</div>",
                div_close,
                div_class_card,
                "<div class='card-title'>Pass Rate</div>",
                div_class_metric_main,
                f"<div class='metric-value'>{pass_rate:.1f}</div>",
                "<div class='metric-unit'>%</div>",
                div_close,
                f"<div class='metric-sub'>Based on {total_tests} scenarios</div>",
                div_close,
                div_class_card,
                "<div class='card-title'>OpenAPI Coverage</div>",
                div_class_metric_main,
                f"<div class='metric-value'>{coverage:.1f}</div>",
                "<div class='metric-unit'>%</div>",
                div_close,
                "<div class='coverage-bar'>",
                f"<div class='coverage-bar-inner' style='width:{coverage:.1f}%'></div>",
                "</div>",
                "<div class='metric-sub'>Endpoints and methods covered by tests</div>",
                div_close,
                "</section>",
            ]
        )
        # Toolbar (filters)
        html_output.extend(
            [
                "<section class='toolbar'>",
                "<div class='toolbar-left'>",
                f"<span>Showing {total_tests} scenario{'s' if total_tests != 1 else ''}</span>",
                div_close,
                "<div class='toolbar-right'>",
                "<label class='filter-label' for='resultFilter'>Result</label>",
                "<select id='resultFilter' class='filter-select' onchange='filterResults()'>",
                "<option value='all'>All</option>",
                "<option value='passed'>Passed</option>",
                "<option value='failed'>Failed</option>",
                "</select>",
                "<label class='filter-label' for='searchInput'>Search</label>",
                "<input id='searchInput' class='filter-input' type='text' "
                "placeholder='Filter by scenario, method, or URL' oninput='filterResults()' />",
                div_close,
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
                "<th>Contract<br/>Validation</th>"
                "<th>Result</th>"
                "</tr></thead><tbody>"
            )

            for idx, r in enumerate(results):
                record = await self._get_responses_for_html(idx, r)
                html_output.append(record)

            html_output.append("</tbody></table></div>")
        else:
            html_output.append(
                "<p class='empty-state'>No test results were produced.</p>"
            )

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

        var matchesSearch = !search || haystack.indexOf(search) !== -1;

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

        return json.dumps(
            {
                "html_report": full_html,
                "xml_report": full_xml,
            }
        )
