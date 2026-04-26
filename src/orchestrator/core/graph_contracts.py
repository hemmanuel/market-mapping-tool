import hashlib
from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator


def build_document_mention_key(source_url: str, canonical_key: str) -> str:
    raw_key = f"{source_url}\n{canonical_key}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class GraphDocumentReference(BaseModel):
    document_id: str
    title: Optional[str] = None
    source_url: Optional[str] = None
    chunk_index: Optional[int] = None


class GraphDocumentSelectionInput(BaseModel):
    site_id: str
    run_id: str
    candidate_document_ids: List[str] = Field(default_factory=list)


class GraphDocumentSelectionOutput(BaseModel):
    documents: List[GraphDocumentReference] = Field(default_factory=list)


class GraphEntityFactSpec(BaseModel):
    entity_name: str = Field(validation_alias=AliasChoices("entity_name", "name"))
    entity_type: str = Field(validation_alias=AliasChoices("entity_type", "type"))
    normalized_name: Optional[str] = None
    description: Optional[str] = None
    evidence_text: Optional[str] = None
    fact_key: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphRelationshipFactSpec(BaseModel):
    source_entity_name: str = Field(validation_alias=AliasChoices("source_entity_name", "source"))
    target_entity_name: str = Field(validation_alias=AliasChoices("target_entity_name", "target"))
    relationship_type: str = Field(validation_alias=AliasChoices("relationship_type", "type"))
    exact_quote: str
    source_entity_normalized_name: Optional[str] = None
    target_entity_normalized_name: Optional[str] = None
    source_entity_type: Optional[str] = None
    target_entity_type: Optional[str] = None
    fact_key: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphSchemaRelationshipHint(BaseModel):
    source: Optional[str] = None
    type: str
    target: Optional[str] = None

    def to_prompt_hint(self) -> str:
        source = (self.source or "").strip()
        relationship_type = self.type.strip()
        target = (self.target or "").strip()

        if source and target:
            return f"{source} -[{relationship_type}]-> {target}"
        if source:
            return f"{source} -[{relationship_type}]"
        if target:
            return f"{relationship_type} -> {target}"
        return relationship_type


class GraphFactExtractionInput(BaseModel):
    site_id: str
    run_id: str
    niche: Optional[str] = None
    schema_entities: List[str] = Field(default_factory=list)
    schema_relationships: List[GraphSchemaRelationshipHint] = Field(default_factory=list)
    document: GraphDocumentReference
    raw_text: Optional[str] = None

    @field_validator("schema_relationships", mode="before")
    @classmethod
    def normalize_schema_relationships(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []

        if isinstance(value, (str, dict)) or hasattr(value, "model_dump"):
            raw_items = [value]
        else:
            raw_items = list(value)

        normalized: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, str):
                normalized.append({"type": item})
            elif isinstance(item, dict):
                normalized.append(item)
            elif hasattr(item, "model_dump"):
                normalized.append(item.model_dump())
            else:
                raise TypeError(
                    "schema_relationships entries must be strings or mapping-like relationship hints"
                )
        return normalized


class GraphFactExtractionOutput(BaseModel):
    entities: List[GraphEntityFactSpec] = Field(default_factory=list)
    relationships: List[GraphRelationshipFactSpec] = Field(default_factory=list)


class GraphExtractionBarrierInput(BaseModel):
    site_id: str
    run_id: str
    selection_task_id: str
    documents: List[GraphDocumentReference] = Field(default_factory=list)
    poll_count: int = 0


class GraphExtractionBarrierOutput(BaseModel):
    ready: bool
    document_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    poll_count: int = 0


class CanonicalEntityResolutionCandidate(BaseModel):
    graph_entity_fact_id: str
    entity_name: str
    entity_type: str
    normalized_name: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalEntitySpec(BaseModel):
    canonical_name: str
    entity_type: str = Field(validation_alias=AliasChoices("entity_type", "type"))
    canonical_key: Optional[str] = None
    normalized_name: Optional[str] = None
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list, validation_alias=AliasChoices("aliases", "raw_names"))
    resolution_confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalEntityMembershipSpec(BaseModel):
    graph_entity_fact_id: str
    canonical_name: str
    entity_type: str = Field(validation_alias=AliasChoices("entity_type", "type"))
    canonical_key: Optional[str] = None
    resolution_reason: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalEntityResolutionInput(BaseModel):
    entity_facts: List[CanonicalEntityResolutionCandidate] = Field(default_factory=list)


class CanonicalEntityResolutionTaskInput(BaseModel):
    site_id: str
    run_id: str
    selection_task_id: Optional[str] = None
    documents: List[GraphDocumentReference] = Field(default_factory=list)


class CanonicalEntityResolutionOutput(BaseModel):
    canonical_entities: List[CanonicalEntitySpec] = Field(default_factory=list)
    memberships: List[CanonicalEntityMembershipSpec] = Field(default_factory=list)


class PersistGraphFactsResult(BaseModel):
    entity_fact_ids: List[str] = Field(default_factory=list)
    relationship_fact_ids: List[str] = Field(default_factory=list)


class GraphFactExtractionPersistResult(PersistGraphFactsResult):
    document_id: str


class PersistCanonicalEntitiesInput(BaseModel):
    site_id: str
    run_id: str
    selection_task_id: Optional[str] = None
    documents: List[GraphDocumentReference] = Field(default_factory=list)
    canonical_entities: List[CanonicalEntitySpec] = Field(default_factory=list)
    memberships: List[CanonicalEntityMembershipSpec] = Field(default_factory=list)


class PersistCanonicalEntitiesResult(BaseModel):
    canonical_entity_ids: List[str] = Field(default_factory=list)
    membership_ids: List[str] = Field(default_factory=list)


class CanonicalRelationshipSpec(BaseModel):
    source_canonical_key: str
    target_canonical_key: str
    relationship_type: str = Field(validation_alias=AliasChoices("relationship_type", "type"))
    canonical_relationship_key: Optional[str] = None
    normalized_relationship_type: Optional[str] = None
    evidence_count: int = 0
    weight: Optional[float] = None
    quotes: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)
    supporting_fact_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalRelationshipAggregationInput(BaseModel):
    site_id: str
    run_id: str
    selection_task_id: Optional[str] = None
    documents: List[GraphDocumentReference] = Field(default_factory=list)


class CanonicalRelationshipAggregationOutput(BaseModel):
    relationships: List[CanonicalRelationshipSpec] = Field(default_factory=list)


class PersistCanonicalRelationshipsInput(BaseModel):
    site_id: str
    run_id: str
    selection_task_id: Optional[str] = None
    documents: List[GraphDocumentReference] = Field(default_factory=list)
    relationships: List[CanonicalRelationshipSpec] = Field(default_factory=list)


class PersistCanonicalRelationshipsResult(BaseModel):
    canonical_relationship_ids: List[str] = Field(default_factory=list)


class GraphProjectionInput(BaseModel):
    site_id: str
    run_id: str


class ProjectCanonicalEntitiesResult(BaseModel):
    projected_entities: int = 0


class ProjectDocumentMentionsResult(BaseModel):
    projected_documents: int = 0
    projected_mentions: int = 0


class ProjectInteractsWithResult(BaseModel):
    projected_relationships: int = 0


class ProjectSemanticSimilarityResult(BaseModel):
    projected_similarity_edges: int = 0


class CanonicalCommunityMemberSpec(BaseModel):
    canonical_key: str
    canonical_name: Optional[str] = None
    entity_type: Optional[str] = None
    membership_rank: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CanonicalCommunitySpec(BaseModel):
    community_key: Optional[str] = None
    algorithm: str = "louvain"
    algorithm_version: str = "neo4j-gds"
    community_name: Optional[str] = None
    summary: Optional[str] = None
    member_count: int = 0
    relationship_count: int = 0
    members: List[CanonicalCommunityMemberSpec] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CommunitySummarySpec(BaseModel):
    community_key: str
    community_name: str
    summary: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PersistCanonicalCommunitiesResult(BaseModel):
    canonical_community_ids: List[str] = Field(default_factory=list)
    membership_ids: List[str] = Field(default_factory=list)


class ProjectCommunitiesResult(PersistCanonicalCommunitiesResult):
    projected_communities: int = 0
    projected_memberships: int = 0


class ProjectCommunitySummariesResult(BaseModel):
    summarized_communities: int = 0


class PruneGraphResult(BaseModel):
    deleted_documents: int = 0
    deleted_entities: int = 0
    deleted_mentions: int = 0


class PublishGraphReadyResult(BaseModel):
    ready: bool = True
    graph_status: str = "ready"
    canonical_entity_count: int = 0
    document_count: int = 0
    mention_count: int = 0
    relationship_count: int = 0
    similarity_edge_count: int = 0
    community_count: int = 0
    community_membership_count: int = 0
