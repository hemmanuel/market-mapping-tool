from pydantic import BaseModel, Field
from typing import Dict, Any, List
import uuid

class TaskFrame(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_id: str
    task_type: str
    payload: Dict[str, Any]
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    retry_count: int = 0
    max_retries: int = 3

# --- Worker I/O Contracts ---

class MarketSizingInput(BaseModel):
    niche: str

class MarketSizingOutput(BaseModel):
    micro_buckets: List[str]

class ExtractCompaniesInput(BaseModel):
    niche: str
    micro_bucket: str

class ExtractCompaniesOutput(BaseModel):
    companies: List[str]

class EnrichCompanyInput(BaseModel):
    niche: str
    company_name: str

class EnrichCompanyOutput(BaseModel):
    company_profile: dict

class PlanCompanySearchInput(BaseModel):
    niche: str
    company_name: str

class PlanCompanySearchOutput(BaseModel):
    search_queries: List[Dict[str, Any]]
