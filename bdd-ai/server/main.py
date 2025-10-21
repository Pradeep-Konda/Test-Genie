from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from langgraph.graph import StateGraph, END

# --- Import your node logic ---
from nodes.code_analysis import CodeAnalysisNode
from nodes.bdd_generation import BDDGenerationNode
from nodes.test_execution import TestExecutionNode

app = FastAPI(title="BDD Test Agent (LangGraph Workflow)")

# --- Input model --- #
class CodeInput(BaseModel):
    source_code: str

# --- Graph State Model --- #
class GraphState(BaseModel):
    source_code: str
    analysis: Optional[str] = None
    feature_file: Optional[str] = None
    feature_text: Optional[str] = None
    execution_output: Optional[str] = None


# --- Build the LangGraph Workflow --- #
graph = StateGraph(GraphState)

# Register nodes (each node is a callable / class implementing __call__)
graph.add_node("analysis_node", CodeAnalysisNode())
graph.add_node("bdd_node", BDDGenerationNode())
graph.add_node("execute_node", TestExecutionNode())

# Connect flow
graph.add_edge("analysis_node", "bdd_node")
graph.add_edge("bdd_node", "execute_node")
graph.add_edge("execute_node", END)

# Set the entry point
graph.set_entry_point("analysis_node")

# Compile the graph
workflow = graph.compile()


# --- API Endpoint --- #
@app.post("/generate-bdd")
def generate_bdd(code_input: CodeInput):
    try:
        initial_state = {"source_code": code_input.source_code}
        output = workflow.invoke(initial_state)
        # print("output type:", type(output))
        # print("feature text:", output.get("feature_text"))

        return {
            "analysis": output.get("analysis"),
            "feature_text": output.get("feature_text"),
            "execution_output": output.get("execution_output"),
        }
    except Exception as e:
        return {"error": str(e)}
