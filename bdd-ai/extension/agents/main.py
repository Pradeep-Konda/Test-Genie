import io
from nodes.code_analysis import CodeAnalysisNode
from nodes.bdd_generation import BDDGenerationNode
from nodes.test_execution import TestExecutionNode
from dataclasses import dataclass
from typing import Optional
import json
import sys
import os


@dataclass
class GraphState:
    project_path: str
    analysis: Optional[str] = None
    feature_text: Optional[str] = None
    execution_output: Optional[str] = None
    report_message: Optional[str] = None



def run_generation_phase(state: GraphState) -> GraphState:
    analysis_node = CodeAnalysisNode()
    bdd_node = BDDGenerationNode()

    # Agent handles reading files from project_path internally
    state = analysis_node(state)
    state = bdd_node(state)
    return state


def run_execution_phase(state: GraphState) -> GraphState:
    execution_node = TestExecutionNode()
    state = execution_node(state)
    return state


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python main.py <phase> <project_path>"}))
        sys.exit(1)

    phase = sys.argv[1]
    project_path = sys.argv[2]

    if not os.path.exists(project_path):
        print(json.dumps({"error": f"Directory not found: {project_path}"}))
        sys.exit(1)

    state = GraphState(project_path=project_path)

    try:
        if phase == "generate":
            gen_state = run_generation_phase(state)
            print(json.dumps({
                "analysis": gen_state.analysis,
                "feature_text": gen_state.feature_text
            }))
        elif phase == "execute":
            state.feature_text = sys.argv[3]
            state.analysis = sys.argv[4]
            final_state = run_execution_phase(state)
            print(json.dumps({
                "execution_output": final_state.execution_output
            }))
        else:
            print(json.dumps({"error": f"Unknown phase: {phase}"}))
            sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)