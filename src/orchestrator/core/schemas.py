import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskFrame(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: Optional[str] = None
    pipeline_id: str
    parent_task_id: Optional[str] = None
    root_task_id: Optional[str] = None
    task_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    outcome: Optional[str] = None
    payload_schema_version: str = "1"
    worker_version: str = "v1"
    priority: int = 100
    partition_key: Optional[str] = None
    concurrency_class: Optional[str] = None
    dedupe_key: Optional[str] = None
    idempotency_key: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    lease_owner: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    available_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskLease(BaseModel):
    task: TaskFrame
    attempt_id: str

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
    poll_count: int = 0

class EnrichCompanyOutput(BaseModel):
    company_profile: dict = Field(default_factory=dict)
    status: str = "SUCCESS"
    poll_count: int = 0
    document_count: int = 0
    pending_source_tasks: int = 0
    source_document_ids: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)

class PlanCompanySearchInput(BaseModel):
    niche: str
    company_name: str


class SearchQuerySpec(BaseModel):
    query: str
    target_domains: List[str] = Field(default_factory=list)


class PlanCompanySearchOutput(BaseModel):
    search_queries: List[SearchQuerySpec]


class SearchQueryInput(BaseModel):
    niche: str
    company_name: str
    query: str
    target_domains: List[str] = Field(default_factory=list)


class SearchQueryOutput(BaseModel):
    urls: List[str]


class GlobalDedupInput(BaseModel):
    url: str
    niche: str
    company_name: str
    schema_entities: List[str] = Field(default_factory=list)


class GlobalDedupOutput(BaseModel):
    url: str
    should_enqueue_scrape: bool
    cached_chunk_count: int = 0

class ScraperInput(BaseModel):
    url: str
    niche: str
    company_name: Optional[str] = None
    schema_entities: List[str] = Field(default_factory=list)

class ScraperOutput(BaseModel):
    raw_text: str
    storage_object: str | None = None
    status_code: int = 200

class BouncerInput(BaseModel):
    raw_text: str
    url: str
    niche: str
    schema_entities: List[str] = Field(default_factory=list)
    company_name: Optional[str] = None
    storage_object: Optional[str] = None

class BouncerOutput(BaseModel):
    is_relevant: bool
    relevance_reason: str

class VectorStorageInput(BaseModel):
    raw_text: str
    url: str
    storage_object: str | None = None
    company_name: Optional[str] = None

class VectorStorageOutput(BaseModel):
    stored_chunks: int
    document_ids: List[str] = Field(default_factory=list)


class PersistCompanyEnrichmentInput(BaseModel):
    niche: str
    company_name: str
    company_profile: dict
    source_document_ids: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


class PersistCompanyEnrichmentOutput(BaseModel):
    persisted: bool
    company_enrichment_id: Optional[str] = None
    founder_ids: List[str] = Field(default_factory=list)
    company_name: Optional[str] = None


class ProjectCompanyEnrichmentInput(BaseModel):
    company_enrichment_id: str


class ProjectCompanyEnrichmentOutput(BaseModel):
    projected: bool
    projected_companies: int = 0
    projected_founders: int = 0
    company_name: Optional[str] = None
