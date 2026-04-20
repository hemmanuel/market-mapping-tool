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
    
    sites: Mapped[List["Site"]] = relationship(back_populates="tenant")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False) # e.g., "Solid State Batteries"
    description: Mapped[Optional[str]] = mapped_column(Text)
    ontology: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    graph_status: Mapped[str] = mapped_column(String(50), default="idle")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tenant: Mapped["Tenant"] = relationship(back_populates="sites")
    data_sources: Mapped[List["DataSource"]] = relationship(back_populates="site")
    pending_documents: Mapped[List["PendingDocument"]] = relationship(back_populates="site")


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    
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
    documents: Mapped[List["Document"]] = relationship(back_populates="data_source")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Using an embedding dimension of 3072 to match Google's gemini-embedding-001.
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(3072)) 
    
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    data_source: Mapped["DataSource"] = relationship(back_populates="documents")

class PendingDocument(Base):
    __tablename__ = "pending_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    estimated_size: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    site: Mapped["Site"] = relationship(back_populates="pending_documents")
