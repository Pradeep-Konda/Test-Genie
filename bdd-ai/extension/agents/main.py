import io
from nodes.code_analysis import CodeAnalysisNode
from nodes.bdd_generation import BDDGenerationNode
from nodes.test_execution import TestExecutionNode
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import json
import sys
import os


@dataclass
class GraphState:
    """
    State object passed through the BDD generation pipeline.
    
    Attributes:
        project_path: Path to the project being analyzed
        analysis: OpenAPI specification (YAML string)
        feature_text: Generated Gherkin test scenarios
        execution_output: Test execution results (HTML report)
        report_message: Status message for reporting
        evaluation_result: Final BDD quality evaluation from LLM judge
        evaluation_history: List of evaluations from each iteration (for tracking improvement)
    """
    project_path: str
    analysis: Optional[str] = None
    feature_text: Optional[str] = None
    execution_output: Optional[str] = None
    report_message: Optional[str] = None
    # LLM-as-Judge evaluation fields
    evaluation_result: Optional[Dict[str, Any]] = None
    evaluation_history: Optional[List[Dict[str, Any]]] = None



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
            
            # Build output with evaluation results if available
            output = {
                "analysis": gen_state.analysis,
                "feature_text": gen_state.feature_text
            }
            
            # Include LLM-as-Judge evaluation results
            if gen_state.evaluation_result:
                output["evaluation_result"] = gen_state.evaluation_result
            if gen_state.evaluation_history:
                output["evaluation_history"] = gen_state.evaluation_history
            
            print(json.dumps(output))
        elif phase == "execute":
            feature_temp = sys.argv[3]
            if os.path.exists(feature_temp):
            # Read and return existing OpenAPI spec
                with open(feature_temp, "r", encoding="utf-8") as f:
                    updatedFeatureText = f.read()
                state.feature_text = updatedFeatureText

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