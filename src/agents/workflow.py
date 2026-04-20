from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes import (
    planner_node, search_node, global_dedup_node, scrape_node, 
    bouncer_node, vector_storage_node
)

def build_acquisition_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("searcher", search_node)
    workflow.add_node("global_dedup", global_dedup_node)
    workflow.add_node("scraper", scrape_node)
    workflow.add_node("bouncer", bouncer_node)
    workflow.add_node("vector_storage", vector_storage_node)

    # Add edges
    workflow.add_edge("planner", "searcher")

    def check_url_yield(state: AgentState) -> str:
        """Determine the next node based on how many URLs were found."""
        urls = state.get("urls_to_scrape", [])
        attempts = state.get("search_attempts", 0)
        target = state.get("target_urls", 200)
        max_attempts = state.get("max_search_attempts", 5)
        
        # If we found less than target URLs and haven't hit max attempts, try again
        if len(urls) < target and attempts < max_attempts:
            return "planner"
        
        # Otherwise, proceed to deduplication
        return "global_dedup"

    workflow.add_conditional_edges(
        "searcher",
        check_url_yield,
        {
            "planner": "planner",
            "global_dedup": "global_dedup"
        }
    )

    workflow.add_edge("global_dedup", "scraper")
    workflow.add_edge("scraper", "bouncer")

    # Route back to scraper if there are more URLs, or planner if we need more data
    def route_after_processing(state: AgentState):
        if state.get("urls_to_scrape") and len(state["urls_to_scrape"]) > 0:
            return "scraper"
            
        # If queue is empty, check if we hit our target
        relevant_count = state.get("relevant_urls_count", 0)
        target = state.get("target_urls", 200)
        attempts = state.get("search_attempts", 0)
        max_attempts = state.get("max_search_attempts", 5)
        
        if relevant_count < target and attempts < max_attempts:
            return "planner"
            
        return END

    # Conditional logic after bouncer
    def check_relevance(state: AgentState):
        if state.get("is_relevant"):
            return "vector_storage"
        else:
            return route_after_processing(state)

    workflow.add_conditional_edges("bouncer", check_relevance, {"vector_storage": "vector_storage", "scraper": "scraper", "planner": "planner", END: END})

    workflow.add_conditional_edges("vector_storage", route_after_processing, {"scraper": "scraper", "planner": "planner", END: END})

    workflow.set_entry_point("planner")

    return workflow.compile()
