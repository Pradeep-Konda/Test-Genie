from nodes.code_analysis import CodeAnalysisNode
from nodes.bdd_generation import BDDGenerationNode
from nodes.test_execution import TestExecutionNode
from pydantic import BaseModel
from typing import Optional
import json, sys

class GraphState(BaseModel):
    source_code: str
    analysis: Optional[str] = None
    feature_text: Optional[str] = None
    execution_output: Optional[str] = None


def run_generation_phase(source_code: str):
    # create proper model instead of dict
    state = GraphState(source_code=source_code)

    analysis_node = CodeAnalysisNode()
    bdd_node = BDDGenerationNode()
    execution_node = TestExecutionNode()

    # Node-to-node pipeline (Generation phase)
    state = analysis_node(state)
    state = bdd_node(state)

    # Do NOT execute yet — stop here for human review
    return state


def run_execution_phase(state: GraphState):
    execution_node = TestExecutionNode()
    state = execution_node(state)
    return state


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No source code provided"}))
        sys.exit(1)

    source_code = sys.argv[2]
    #print(source_code)
    if not source_code:
        print(json.dumps({"error": "Empty source code"}))
        sys.exit(1)
    # Step 1 — Run generation phase
    gen_state = run_generation_phase(source_code)

    # (Here you could persist gen_state.feature_text to disk for human review)
    # print("===== HUMAN REVIEW REQUIRED =====")
    # print(gen_state.feature_text)

    # Step 2 — After human approval, run execution phase
    final_state = run_execution_phase(gen_state)

    print(json.dumps({
        "analysis": final_state.analysis,
        "feature_text": final_state.feature_text,
        "execution_output": final_state.execution_output
    }))
