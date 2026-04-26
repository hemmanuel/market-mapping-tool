from typing import TypedDict, List, Dict, Any, Optional

class SearchQuery(TypedDict):
    query: str
    target_domains: List[str]

class AgentState(TypedDict):
    pipeline_id: str
    niche: str
    schema_entities: List[str]
    schema_relationships: List[Dict[str, str]]
    
    # Discovery State
    micro_buckets: List[str]
    discovered_companies: List[str]
    
    # Execution State
    search_queries: List[SearchQuery]
    search_attempts: int
    target_urls: int
    max_search_attempts: int
    urls_to_scrape: List[str]
    cached_urls: List[str]
    current_url: Optional[str]
    raw_text: Optional[str]
    storage_object: Optional[str]
    search_feedback: List[str]
    relevant_urls_count: int
    
    # Validation State
    is_relevant: bool
    relevance_reason: Optional[str]
    
    # Final Storage
    stored_chunks: int
