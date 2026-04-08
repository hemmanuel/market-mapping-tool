from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes import (
    planner_node, search_node, scrape_node, 
    bouncer_node, extractor_node, validator_node, storage_node
)

def build_acquisition_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("searcher", search_node)
    workflow.add_node("scraper", scrape_node)
    workflow.add_node("bouncer", bouncer_node)
    workflow.add_node("extractor", extractor_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("storage", storage_node)

    # Add edges
    workflow.add_edge("planner", "searcher")
    workflow.add_edge("searcher", "scraper")
    workflow.add_edge("scraper", "bouncer")

    # Conditional logic after bouncer
    def check_relevance(state: AgentState):
        if state["is_relevant"]:
            return "extractor"
        else:
            return END

    workflow.add_conditional_edges("bouncer", check_relevance, {"extractor": "extractor", END: END})

    workflow.add_edge("extractor", "validator")

    # Conditional logic after validation
    def check_validation(state: AgentState):
        if state["is_valid"]:
            return "storage"
        else:
            # If invalid, we could route back to extractor for correction, but for now we'll just end or log
            return END

    workflow.add_conditional_edges("validator", check_validation, {"storage": "storage", END: END})
    
    workflow.add_edge("storage", END)

    workflow.set_entry_point("planner")

    return workflow.compile()
