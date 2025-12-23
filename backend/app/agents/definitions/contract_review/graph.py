from langgraph.graph import StateGraph, END
from app.agents.definitions.contract_review.state import ReviewState
from app.agents.definitions.contract_review.nodes import (
    loader_node,
    rule_check_node,
    llm_audit_node,
    synthesizer_node
)

def create_contract_review_graph():
    workflow = StateGraph(ReviewState)
    
    # Add Nodes
    workflow.add_node("loader", loader_node)
    workflow.add_node("rule_check", rule_check_node)
    workflow.add_node("llm_audit", llm_audit_node)
    workflow.add_node("synthesizer", synthesizer_node)
    
    # Add Edges
    workflow.set_entry_point("loader")
    workflow.add_edge("loader", "rule_check")
    workflow.add_edge("rule_check", "llm_audit")
    workflow.add_edge("llm_audit", "synthesizer")
    workflow.add_edge("synthesizer", END)
    
    return workflow.compile()

review_graph = create_contract_review_graph()
