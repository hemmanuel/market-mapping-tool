import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.relational import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", index=True)
    objective: Mapped[str] = mapped_column(String(100), nullable=False, default="acquire")
    orchestration_version: Mapped[str] = mapped_column(String(100), nullable=False, default="bespoke-v2")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    site = relationship("Site")
    workflow_context = relationship("WorkflowContext", back_populates="run", uselist=False, cascade="all, delete-orphan")
    task_frames = relationship("OrchestrationTaskFrameRecord", back_populates="run", cascade="all, delete-orphan")
    task_attempts = relationship("TaskAttempt", back_populates="run", cascade="all, delete-orphan")
    task_artifacts = relationship("TaskArtifact", back_populates="run", cascade="all, delete-orphan")
    outbox_events = relationship("OutboxEvent", back_populates="run", cascade="all, delete-orphan")
    dead_letter_tasks = relationship("DeadLetterTask", back_populates="run", cascade="all, delete-orphan")


class WorkflowContext(Base):
    __tablename__ = "workflow_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), unique=True, index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    context_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    run = relationship("PipelineRun", back_populates="workflow_context")
    site = relationship("Site")


class OrchestrationTaskFrameRecord(Base):
    __tablename__ = "orchestration_task_frames"
    __table_args__ = (
        UniqueConstraint("run_id", "task_type", "idempotency_key", name="uq_task_frames_run_task_idempotency"),
        Index("ix_task_frames_run_status_available", "run_id", "status", "available_at"),
        Index("ix_task_frames_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    parent_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("orchestration_task_frames.id"))
    root_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload_schema_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    worker_version: Mapped[str] = mapped_column(String(100), nullable=False, default="v1")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    partition_key: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    concurrency_class: Mapped[Optional[str]] = mapped_column(String(100))
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(512))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(100))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[Optional[str]] = mapped_column(String(255))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[Optional[str]] = mapped_column(String(255))
    last_error_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    run = relationship("PipelineRun", back_populates="task_frames")
    site = relationship("Site")
    parent_task = relationship("OrchestrationTaskFrameRecord", remote_side=[id], back_populates="child_tasks")
    child_tasks = relationship("OrchestrationTaskFrameRecord", back_populates="parent_task")
    attempts = relationship("TaskAttempt", back_populates="task_frame", cascade="all, delete-orphan")
    artifacts = relationship("TaskArtifact", back_populates="task_frame", cascade="all, delete-orphan")


class TaskAttempt(Base):
    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("task_frame_id", "attempt_number", name="uq_task_attempt_number"),
        Index("ix_task_attempts_run_status", "run_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="started")
    worker_version: Mapped[Optional[str]] = mapped_column(String(100))
    lease_owner: Mapped[Optional[str]] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[Optional[str]] = mapped_column(String(100))
    error_code: Mapped[Optional[str]] = mapped_column(String(255))
    error_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    output_json: Mapped[Optional[dict]] = mapped_column(JSONB)

    task_frame = relationship("OrchestrationTaskFrameRecord", back_populates="attempts")
    run = relationship("PipelineRun", back_populates="task_attempts")
    site = relationship("Site")


class TaskArtifact(Base):
    __tablename__ = "task_artifacts"
    __table_args__ = (
        Index("ix_task_artifacts_run_type", "run_id", "artifact_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_frame_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orchestration_task_frames.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_key: Mapped[str] = mapped_column(String(512), nullable=False)
    uri: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task_frame = relationship("OrchestrationTaskFrameRecord", back_populates="artifacts")
    run = relationship("PipelineRun", back_populates="task_artifacts")
    site = relationship("Site")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_site_status_created", "site_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    task_frame_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("orchestration_task_frames.id"))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run = relationship("PipelineRun", back_populates="outbox_events")
    site = relationship("Site")


class DeadLetterTask(Base):
    __tablename__ = "dead_letter_tasks"
    __table_args__ = (
        Index("ix_dead_letter_tasks_run_created", "run_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"), index=True)
    task_frame_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("orchestration_task_frames.id"))
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(String(255))
    error_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run = relationship("PipelineRun", back_populates="dead_letter_tasks")
    site = relationship("Site")
