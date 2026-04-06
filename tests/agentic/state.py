from typing import List, Dict, Any, TypedDict, Optional
from pydantic import BaseModel, Field

class TestConfig(BaseModel):
    target_url: str = Field(default="https://market-mapping-tool.vercel.app/")
    target_niche: str = Field(default="Spacetech")
    max_conversation_turns: int = Field(default=5)
    user_persona: str = Field(default="You are an early-stage VC looking to map the spacetech industry broadly. You are a bit vague at first. If the consultant asks you specific questions about what entities or relationships you want, answer them naturally, but try to keep the scope broad. Do not break character.")
    expected_entities: List[str] = Field(default=["Startup", "Founder", "Investor", "FundingRound", "Technology", "Contract"])
    expected_relationships: List[Dict[str, str]] = Field(default=[
        {"source": "Founder", "type": "FOUNDED", "target": "Startup"},
        {"source": "Investor", "type": "INVESTED_IN", "target": "FundingRound"},
        {"source": "FundingRound", "type": "RAISED_BY", "target": "Startup"},
        {"source": "Startup", "type": "DEVELOPS", "target": "Technology"},
        {"source": "Startup", "type": "AWARDED", "target": "Contract"}
    ])

class TesterState(TypedDict):
    config: TestConfig
    browser: Optional[Any]  # Playwright Browser
    context: Optional[Any]  # Playwright BrowserContext
    page: Optional[Any]     # Playwright Page
    logs: List[str]
    status: str             # "pending", "pass", "fail"
