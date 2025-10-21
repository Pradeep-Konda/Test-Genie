class ResultNode:
    def __call__(self, data):
        return {
            "analysis": data.analysis,
            "feature_text": data.feature_text,
            "execution_output": data.execution_output
        }