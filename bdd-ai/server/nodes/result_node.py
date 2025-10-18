class ResultNode:
    def __call__(self, data):
        return {
            "feature_text": data.feature_file,
            "execution_output": data.execution_output
        }