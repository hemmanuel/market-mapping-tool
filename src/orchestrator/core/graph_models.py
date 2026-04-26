import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.relational import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GraphEntityFact(Base):
    __tablename__ = "graph_entity_facts"
    __table_args__ = (
        UniqueConstraint("run_id", "document_id", "fact_key", name="uq_graph_entity_facts_run_document_fact"),
        Index("ix_graph_entity_facts_site_run", "site_id", "run_id"),
        Index("ix_graph_entity_facts_run_entity_type", "run_id", "entity_type"),
        Index("ix_graph_entity_facts_run_normalized_name", "run_id", "normalized_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    fact_key: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    canonical_memberships = relationship(
        "CanonicalEntityMembership",
        back_populates="graph_entity_fact",
        cascade="all, delete-orphan",
    )


class GraphRelationshipFact(Base):
    __tablename__ = "graph_relationship_facts"
    __table_args__ = (
        UniqueConstraint("run_id", "document_id", "fact_key", name="uq_graph_relationship_facts_run_document_fact"),
        Index("ix_graph_relationship_facts_site_run", "site_id", "run_id"),
        Index("ix_graph_relationship_facts_run_rel_type", "run_id", "relationship_type"),
        Index(
            "ix_graph_relationship_facts_run_source_target",
            "run_id",
            "source_entity_normalized_name",
            "target_entity_normalized_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    source_entity_fact_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("graph_entity_facts.id"), index=True)
    target_entity_fact_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("graph_entity_facts.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    fact_key: Mapped[str] = mapped_column(String(512), nullable=False)
    source_entity_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_entity_normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_entity_type: Mapped[Optional[str]] = mapped_column(String(255))
    target_entity_name: Mapped[str] = mapped_column(String(512), nullable=False)
    target_entity_normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    target_entity_type: Mapped[Optional[str]] = mapped_column(String(255))
    relationship_type: Mapped[str] = mapped_column(String(255), nullable=False)
    exact_quote: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source_entity_fact = relationship("GraphEntityFact", foreign_keys=[source_entity_fact_id])
    target_entity_fact = relationship("GraphEntityFact", foreign_keys=[target_entity_fact_id])


class CanonicalGraphEntity(Base):
    __tablename__ = "canonical_entities"
    __table_args__ = (
        UniqueConstraint("run_id", "canonical_key", name="uq_canonical_entities_run_key"),
        Index("ix_canonical_entities_site_run", "site_id", "run_id"),
        Index("ix_canonical_entities_run_normalized_name", "run_id", "normalized_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    aliases_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    resolution_confidence: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    memberships = relationship(
        "CanonicalEntityMembership",
        back_populates="canonical_entity",
        cascade="all, delete-orphan",
    )
    community_memberships = relationship(
        "CanonicalCommunityMembership",
        back_populates="canonical_entity",
        cascade="all, delete-orphan",
    )


class CanonicalEntityMembership(Base):
    __tablename__ = "canonical_entity_memberships"
    __table_args__ = (
        UniqueConstraint("run_id", "graph_entity_fact_id", name="uq_canonical_entity_memberships_run_fact"),
        Index("ix_canonical_entity_memberships_site_run", "site_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    graph_entity_fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("graph_entity_facts.id"), index=True)
    resolution_reason: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    canonical_entity = relationship("CanonicalGraphEntity", back_populates="memberships")
    graph_entity_fact = relationship("GraphEntityFact", back_populates="canonical_memberships")


class CanonicalGraphRelationship(Base):
    __tablename__ = "canonical_relationships"
    __table_args__ = (
        UniqueConstraint("run_id", "canonical_relationship_key", name="uq_canonical_relationships_run_key"),
        Index("ix_canonical_relationships_site_run", "site_id", "run_id"),
        Index("ix_canonical_relationships_run_rel_type", "run_id", "relationship_type"),
        Index(
            "ix_canonical_relationships_run_source_target",
            "run_id",
            "source_canonical_key",
            "target_canonical_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    source_canonical_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    target_canonical_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    canonical_relationship_key: Mapped[str] = mapped_column(String(512), nullable=False)
    source_canonical_key: Mapped[str] = mapped_column(String(512), nullable=False)
    target_canonical_key: Mapped[str] = mapped_column(String(512), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_relationship_type: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quotes_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_urls_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    supporting_fact_ids_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    source_canonical_entity = relationship("CanonicalGraphEntity", foreign_keys=[source_canonical_entity_id])
    target_canonical_entity = relationship("CanonicalGraphEntity", foreign_keys=[target_canonical_entity_id])


class CanonicalGraphCommunity(Base):
    __tablename__ = "canonical_communities"
    __table_args__ = (
        UniqueConstraint("run_id", "community_key", name="uq_canonical_communities_run_key"),
        Index("ix_canonical_communities_site_run", "site_id", "run_id"),
        Index("ix_canonical_communities_run_algorithm", "run_id", "algorithm"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    community_key: Mapped[str] = mapped_column(String(512), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(100), nullable=False, default="louvain")
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False, default="neo4j-gds")
    community_name: Mapped[Optional[str]] = mapped_column(String(255))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relationship_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    memberships = relationship(
        "CanonicalCommunityMembership",
        back_populates="canonical_community",
        cascade="all, delete-orphan",
    )


class CanonicalCommunityMembership(Base):
    __tablename__ = "canonical_community_memberships"
    __table_args__ = (
        UniqueConstraint("run_id", "canonical_entity_id", name="uq_canonical_community_memberships_run_entity"),
        Index("ix_canonical_community_memberships_site_run", "site_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    canonical_community_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_communities.id"), index=True)
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_entities.id"), index=True)
    membership_rank: Mapped[Optional[int]] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    canonical_community = relationship("CanonicalGraphCommunity", back_populates="memberships")
    canonical_entity = relationship("CanonicalGraphEntity", back_populates="community_memberships")
