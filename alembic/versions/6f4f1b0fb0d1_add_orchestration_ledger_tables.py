"""add orchestration ledger tables

Revision ID: 6f4f1b0fb0d1
Revises: 8cec9ce972b2
Create Date: 2026-04-23 10:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6f4f1b0fb0d1"
down_revision: Union[str, Sequence[str], None] = "8cec9ce972b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("objective", sa.String(length=100), nullable=False),
        sa.Column("orchestration_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_runs_site_id"), "pipeline_runs", ["site_id"], unique=False)
    op.create_index(op.f("ix_pipeline_runs_status"), "pipeline_runs", ["status"], unique=False)

    op.create_table(
        "workflow_contexts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(op.f("ix_workflow_contexts_run_id"), "workflow_contexts", ["run_id"], unique=True)
    op.create_index(op.f("ix_workflow_contexts_site_id"), "workflow_contexts", ["site_id"], unique=False)

    op.create_table(
        "orchestration_task_frames",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("parent_task_id", sa.UUID(), nullable=True),
        sa.Column("root_task_id", sa.UUID(), nullable=True),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_schema_version", sa.String(length=50), nullable=False),
        sa.Column("worker_version", sa.String(length=100), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("partition_key", sa.String(length=255), nullable=True),
        sa.Column("concurrency_class", sa.String(length=100), nullable=True),
        sa.Column("dedupe_key", sa.String(length=512), nullable=True),
        sa.Column("idempotency_key", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("outcome", sa.String(length=100), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=255), nullable=True),
        sa.Column("last_error_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_task_id"], ["orchestration_task_frames.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "task_type", "idempotency_key", name="uq_task_frames_run_task_idempotency"),
    )
    op.create_index(op.f("ix_orchestration_task_frames_partition_key"), "orchestration_task_frames", ["partition_key"], unique=False)
    op.create_index(op.f("ix_orchestration_task_frames_root_task_id"), "orchestration_task_frames", ["root_task_id"], unique=False)
    op.create_index(op.f("ix_orchestration_task_frames_run_id"), "orchestration_task_frames", ["run_id"], unique=False)
    op.create_index(op.f("ix_orchestration_task_frames_site_id"), "orchestration_task_frames", ["site_id"], unique=False)
    op.create_index(op.f("ix_orchestration_task_frames_status"), "orchestration_task_frames", ["status"], unique=False)
    op.create_index(op.f("ix_orchestration_task_frames_task_type"), "orchestration_task_frames", ["task_type"], unique=False)
    op.create_index("ix_task_frames_run_status_available", "orchestration_task_frames", ["run_id", "status", "available_at"], unique=False)
    op.create_index("ix_task_frames_status_lease", "orchestration_task_frames", ["status", "lease_expires_at"], unique=False)

    op.create_table(
        "task_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("worker_version", sa.String(length=100), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.Column("error_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_frame_id", "attempt_number", name="uq_task_attempt_number"),
    )
    op.create_index(op.f("ix_task_attempts_run_id"), "task_attempts", ["run_id"], unique=False)
    op.create_index(op.f("ix_task_attempts_site_id"), "task_attempts", ["site_id"], unique=False)
    op.create_index(op.f("ix_task_attempts_task_frame_id"), "task_attempts", ["task_frame_id"], unique=False)
    op.create_index("ix_task_attempts_run_status", "task_attempts", ["run_id", "status"], unique=False)

    op.create_table(
        "task_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("artifact_type", sa.String(length=100), nullable=False),
        sa.Column("artifact_key", sa.String(length=512), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_artifacts_run_id"), "task_artifacts", ["run_id"], unique=False)
    op.create_index(op.f("ix_task_artifacts_site_id"), "task_artifacts", ["site_id"], unique=False)
    op.create_index(op.f("ix_task_artifacts_task_frame_id"), "task_artifacts", ["task_frame_id"], unique=False)
    op.create_index("ix_task_artifacts_run_type", "task_artifacts", ["run_id", "artifact_type"], unique=False)

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_outbox_events_run_id"), "outbox_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_outbox_events_site_id"), "outbox_events", ["site_id"], unique=False)
    op.create_index("ix_outbox_events_site_status_created", "outbox_events", ["site_id", "status", "created_at"], unique=False)

    op.create_table(
        "dead_letter_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=True),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.Column("error_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dead_letter_tasks_run_id"), "dead_letter_tasks", ["run_id"], unique=False)
    op.create_index(op.f("ix_dead_letter_tasks_site_id"), "dead_letter_tasks", ["site_id"], unique=False)
    op.create_index("ix_dead_letter_tasks_run_created", "dead_letter_tasks", ["run_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_dead_letter_tasks_run_created", table_name="dead_letter_tasks")
    op.drop_index(op.f("ix_dead_letter_tasks_site_id"), table_name="dead_letter_tasks")
    op.drop_index(op.f("ix_dead_letter_tasks_run_id"), table_name="dead_letter_tasks")
    op.drop_table("dead_letter_tasks")

    op.drop_index("ix_outbox_events_site_status_created", table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_site_id"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_run_id"), table_name="outbox_events")
    op.drop_table("outbox_events")

    op.drop_index("ix_task_artifacts_run_type", table_name="task_artifacts")
    op.drop_index(op.f("ix_task_artifacts_task_frame_id"), table_name="task_artifacts")
    op.drop_index(op.f("ix_task_artifacts_site_id"), table_name="task_artifacts")
    op.drop_index(op.f("ix_task_artifacts_run_id"), table_name="task_artifacts")
    op.drop_table("task_artifacts")

    op.drop_index("ix_task_attempts_run_status", table_name="task_attempts")
    op.drop_index(op.f("ix_task_attempts_task_frame_id"), table_name="task_attempts")
    op.drop_index(op.f("ix_task_attempts_site_id"), table_name="task_attempts")
    op.drop_index(op.f("ix_task_attempts_run_id"), table_name="task_attempts")
    op.drop_table("task_attempts")

    op.drop_index("ix_task_frames_status_lease", table_name="orchestration_task_frames")
    op.drop_index("ix_task_frames_run_status_available", table_name="orchestration_task_frames")
    op.drop_index(op.f("ix_orchestration_task_frames_task_type"), table_name="orchestration_task_frames")
    op.drop_index(op.f("ix_orchestration_task_frames_status"), table_name="orchestration_task_frames")
    op.drop_index(op.f("ix_orchestration_task_frames_site_id"), table_name="orchestration_task_frames")
    op.drop_index(op.f("ix_orchestration_task_frames_run_id"), table_name="orchestration_task_frames")
    op.drop_index(op.f("ix_orchestration_task_frames_root_task_id"), table_name="orchestration_task_frames")
    op.drop_index(op.f("ix_orchestration_task_frames_partition_key"), table_name="orchestration_task_frames")
    op.drop_table("orchestration_task_frames")

    op.drop_index(op.f("ix_workflow_contexts_site_id"), table_name="workflow_contexts")
    op.drop_index(op.f("ix_workflow_contexts_run_id"), table_name="workflow_contexts")
    op.drop_table("workflow_contexts")

    op.drop_index(op.f("ix_pipeline_runs_status"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_site_id"), table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
