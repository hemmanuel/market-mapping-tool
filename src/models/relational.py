import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, ForeignKey, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

class Base(DeclarativeBase):
    pass

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auth_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True) # Clerk user_id
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    sites: Mapped[List["Site"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False) # e.g., "Solid State Batteries"
    description: Mapped[Optional[str]] = mapped_column(Text)
    ontology: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tenant: Mapped["Tenant"] = relationship(back_populates="sites")
    data_sources: Mapped[List["DataSource"]] = relationship(back_populates="site", cascade="all, delete-orphan")


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    
    # Dynamic identifier: "rss", "api_endpoint", "s3_bucket", "user_upload"
    source_type: Mapped[str] = mapped_column(String(100), nullable=False) 
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # The JSONB config holds EVERYTHING needed to connect and parse.
    # e.g., {"url": "...", "headers": {"Auth": "..."}, "pagination_strategy": "cursor"}
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict) 
    
    # If tenants can define their own data schemas, we can store the expected 
    # output schema here so the LLM knows what to extract during ingestion.
    extraction_schema: Mapped[Optional[dict]] = mapped_column(JSONB) 

    cadence_cron: Mapped[str] = mapped_column(String(100), nullable=False, default="0 0 * * *")
    status: Mapped[str] = mapped_column(String(50), default="active")
    
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    site: Mapped["Site"] = relationship(back_populates="data_sources")
    documents: Mapped[List["Document"]] = relationship(back_populates="data_source", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Using an embedding dimension of 1536 as a placeholder. 
    # This should be updated to match the local LLM embedding model (e.g., 768 for nomic).
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536)) 
    
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    data_source: Mapped["DataSource"] = relationship(back_populates="documents")
