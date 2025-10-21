import subprocess


class TestExecutionNode:
    def __call__(self, data):
        result = subprocess.run(["behave", "behave_tests/features/"], capture_output=True, text=True)
        data.execution_output = result.stdout
        # print(data.execution_output)
        print("=====TEST EXECUTION COMPLETE=====")
        return data