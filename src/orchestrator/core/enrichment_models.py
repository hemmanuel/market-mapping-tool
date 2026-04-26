import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.relational import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyEnrichmentProfile(Base):
    __tablename__ = "company_enrichment_profiles"
    __table_args__ = (
        UniqueConstraint("site_id", "normalized_company_name", name="uq_company_enrichment_profiles_site_company"),
        Index("ix_company_enrichment_profiles_site_stage", "site_id", "stage_estimate"),
        Index("ix_company_enrichment_profiles_site_sector", "site_id", "primary_sector"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(512))
    primary_url: Mapped[Optional[str]] = mapped_column(String(2048))
    full_description: Mapped[Optional[str]] = mapped_column(Text)
    pitch_summary: Mapped[Optional[str]] = mapped_column(Text)
    primary_sector: Mapped[Optional[str]] = mapped_column(String(255))
    business_model: Mapped[Optional[str]] = mapped_column(String(255))
    customer_type: Mapped[Optional[str]] = mapped_column(String(255))
    investment_thesis_one_liner: Mapped[Optional[str]] = mapped_column(Text)
    tangibility_score: Mapped[Optional[int]] = mapped_column(Integer)
    venture_scale_score: Mapped[Optional[float]] = mapped_column(Float)
    stage_estimate: Mapped[Optional[str]] = mapped_column(String(255))
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    company_twitter_url: Mapped[Optional[str]] = mapped_column(String(2048))
    taxonomy_l1: Mapped[Optional[str]] = mapped_column(String(255))
    taxonomy_l2: Mapped[Optional[str]] = mapped_column(String(255))
    taxonomy_l3: Mapped[Optional[str]] = mapped_column(String(255))
    tech_stack_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    dimension_scores_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    vc_dossier_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    strategic_analysis_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metric_rationales_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_document_ids_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_urls_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    founders = relationship(
        "CompanyEnrichmentFounder",
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class CompanyEnrichmentFounder(Base):
    __tablename__ = "company_enrichment_founders"
    __table_args__ = (
        UniqueConstraint("profile_id", "name", "role", name="uq_company_enrichment_founders_profile_name_role"),
        Index("ix_company_enrichment_founders_site_profile", "site_id", "profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company_enrichment_profiles.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    task_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_attempts.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(255))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    hometown: Mapped[Optional[str]] = mapped_column(String(255))
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(2048))
    twitter_url: Mapped[Optional[str]] = mapped_column(String(2048))
    previous_companies_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    education_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_technical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile = relationship("CompanyEnrichmentProfile", back_populates="founders")
