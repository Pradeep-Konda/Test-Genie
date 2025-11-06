import subprocess
import os
import re
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


# class TestExecutionNode:
#     def __call__(self, data):
#         result = subprocess.run(["behave", "behave_tests/features/"], capture_output=True, text=True)
#         data.execution_output = result.stdout
#         # print(data.execution_output)
#         # print("=====TEST EXECUTION COMPLETE=====")
#         return data
    

class TestExecutionNode:
    def __init__(self, llm=None):
        print("bdjbfdjdfjjjdjdjnjd-------------")

        # ✅ Initialize GPT model
        self.llm = ChatOpenAI(model="gpt-4.1", temperature=0)

        # Define tool that LangChain agent will use
        self.tools = [
            Tool(
                name="Generatetestreports",
                func=self.generate_report_multiple_formats,
                description="Generate test execution reports in HTML and JUnit XML format."
            )
        ]

        # System instructions to the agent
        self.system_prompt = """
        Generate test reports in multiple formats based on raw Behave test execution output.

        Each report must include:
        - Summary of test results (passed, failed, skipped)
        - Detailed breakdown for each test case
        - Request/Response payloads for failed cases

        """

        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt
        )


        # ---- Tool Function ---- #
    def generate_report_multiple_formats(self, execution_output: str):
        print("generatete htmlmdnknsdnsnd")
        """
        Converts Behave test output into HTML and JUnit XML reports.
        """
        os.makedirs("reports", exist_ok=True)

        html_path = "reports/html_test_report.html"
        junit_path = "reports/junitXML_test_report.xml"

        passed = failed = skipped = 0

        for line in execution_output.splitlines():
            # Match patterns like "5 scenarios (4 passed, 1 failed, 0 skipped)"
            if "scenarios" in line and "(" in line:
                match = re.search(r"\((.*?)\)", line)
                if match:
                    summary = match.group(1)
                    if "passed" in summary:
                        passed_match = re.search(r"(\d+)\s+passed", summary)
                        if passed_match:
                            passed = int(passed_match.group(1))
                    if "failed" in summary:
                        failed_match = re.search(r"(\d+)\s+failed", summary)
                        if failed_match:
                            failed = int(failed_match.group(1))
                    if "skipped" in summary:
                        skipped_match = re.search(r"(\d+)\s+skipped", summary)
                        if skipped_match:
                            skipped = int(skipped_match.group(1))


        # --- HTML report generation ---
        html_content = f"""
        <html>
        <head><title>Behave Test Report</title></head>
        <body>
        <h1>Behave Test Execution Report</h1>
        <h2>Summary</h2>
        <ul>
            <li>Passed: {passed}</li>
            <li>Failed: {failed}</li>
            <li>Skipped: {skipped}</li>
        </ul>
        <h2>Full Execution Log</h2>
        <pre>{execution_output}</pre>
        </body>
        </html>
        """
        with open(html_path, "w") as f:
            f.write(html_content)

        # --- JUnit XML report generation ---
        junit_content = f"""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="Behave Tests" tests="{passed + failed + skipped}" failures="{failed}" skipped="{skipped}">
        <properties></properties>
        <system-out><![CDATA[{execution_output}]]></system-out>
        </testsuite>
        """
        with open(junit_path, "w") as f:
            f.write(junit_content)

        return f"✅ Reports generated:\n- {html_path}\n- {junit_path}"

    def __call__(self, data):
        # Run Behave tests
        result = subprocess.run(["behave", "behave_tests/features/"], capture_output=True, text=True)

        data.execution_output = result.stdout
        print(data.execution_output,"execution_output")

        messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"Generate reports for this test output:\n\n{data.execution_output}")
            ]

            # Run the agent
        data.report_message = self.agent.invoke({"messages": messages})

        print("===== TEST EXECUTION COMPLETE =====")
        return data