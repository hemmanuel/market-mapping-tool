from typing import TypedDict, List, Dict, Any, Optional

class SearchQuery(TypedDict):
    query: str
    target_domains: List[str]

class AgentState(TypedDict):
    pipeline_id: str
    niche: str
    schema_entities: List[str]
    schema_relationships: List[Dict[str, str]]
    
    # Execution State
    search_queries: List[SearchQuery]
    urls_to_scrape: List[str]
    current_url: Optional[str]
    raw_text: Optional[str]
    
    # Validation State
    is_relevant: bool
    relevance_reason: Optional[str]
    
    # Final Storage
    stored_chunks: int
