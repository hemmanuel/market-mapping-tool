from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes import (
    planner_node, search_node, scrape_node, 
    bouncer_node, vector_storage_node
)

def build_acquisition_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("searcher", search_node)
    workflow.add_node("scraper", scrape_node)
    workflow.add_node("bouncer", bouncer_node)
    workflow.add_node("vector_storage", vector_storage_node)

    # Add edges
    workflow.add_edge("planner", "searcher")
    workflow.add_edge("searcher", "scraper")
    workflow.add_edge("scraper", "bouncer")

    # Route back to scraper if there are more URLs
    def route_after_processing(state: AgentState):
        if state.get("urls_to_scrape") and len(state["urls_to_scrape"]) > 0:
            return "scraper"
        return END

    # Conditional logic after bouncer
    def check_relevance(state: AgentState):
        if state.get("is_relevant"):
            return "vector_storage"
        else:
            return route_after_processing(state)

    workflow.add_conditional_edges("bouncer", check_relevance, {"vector_storage": "vector_storage", "scraper": "scraper", END: END})

    workflow.add_conditional_edges("vector_storage", route_after_processing, {"scraper": "scraper", END: END})

    workflow.set_entry_point("planner")

    return workflow.compile()
