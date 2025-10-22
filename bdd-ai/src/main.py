import sys
import json
from nodes.code_analysis import CodeAnalysisNode
from nodes.bdd_generation import BDDGenerationNode
from nodes.test_execution import TestExecutionNode
from langgraph.graph import StateGraph, END
from typing import Optional
from pydantic import BaseModel

class GraphState(BaseModel):
    source_code: str
    analysis: Optional[str] = None
    feature_text: Optional[str] = None
    execution_output: Optional[str] = None

graph = StateGraph(GraphState)
graph.add_node("analysis_node", CodeAnalysisNode())
graph.add_node("bdd_node", BDDGenerationNode())
graph.add_node("execute_node", TestExecutionNode())
graph.add_edge("analysis_node", "bdd_node")
graph.add_edge("bdd_node", "execute_node")
graph.add_edge("execute_node", END)
graph.set_entry_point("analysis_node")
workflow = graph.compile()

def generateBDD(source_code: str):
    initial_state = {"source_code": source_code}
    result = workflow.invoke(initial_state)
    # Ensure JSON serializable dict
    return {
        "analysis": result.get("analysis"),
        "feature_text": result.get("feature_text"),
        "execution_output": result.get("execution_output")
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No source code provided"}))
        sys.exit(1)
    source_code = sys.argv[1]
    output = generateBDD(source_code)
    #print(output.get("execution_output"))
    print(json.dumps(output))
