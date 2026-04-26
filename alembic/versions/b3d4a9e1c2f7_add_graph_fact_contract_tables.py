"""add graph fact contract tables

Revision ID: b3d4a9e1c2f7
Revises: 6f4f1b0fb0d1
Create Date: 2026-04-23 12:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b3d4a9e1c2f7"
down_revision: Union[str, Sequence[str], None] = "6f4f1b0fb0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_entity_facts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("fact_key", sa.String(length=512), nullable=False),
        sa.Column("entity_name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name", sa.String(length=512), nullable=False),
        sa.Column("entity_type", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "document_id", "fact_key", name="uq_graph_entity_facts_run_document_fact"),
    )
    op.create_index(op.f("ix_graph_entity_facts_document_id"), "graph_entity_facts", ["document_id"], unique=False)
    op.create_index(op.f("ix_graph_entity_facts_run_id"), "graph_entity_facts", ["run_id"], unique=False)
    op.create_index(op.f("ix_graph_entity_facts_site_id"), "graph_entity_facts", ["site_id"], unique=False)
    op.create_index(op.f("ix_graph_entity_facts_task_attempt_id"), "graph_entity_facts", ["task_attempt_id"], unique=False)
    op.create_index(op.f("ix_graph_entity_facts_task_frame_id"), "graph_entity_facts", ["task_frame_id"], unique=False)
    op.create_index("ix_graph_entity_facts_site_run", "graph_entity_facts", ["site_id", "run_id"], unique=False)
    op.create_index("ix_graph_entity_facts_run_entity_type", "graph_entity_facts", ["run_id", "entity_type"], unique=False)
    op.create_index("ix_graph_entity_facts_run_normalized_name", "graph_entity_facts", ["run_id", "normalized_name"], unique=False)

    op.create_table(
        "graph_relationship_facts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("source_entity_fact_id", sa.UUID(), nullable=True),
        sa.Column("target_entity_fact_id", sa.UUID(), nullable=True),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("fact_key", sa.String(length=512), nullable=False),
        sa.Column("source_entity_name", sa.String(length=512), nullable=False),
        sa.Column("source_entity_normalized_name", sa.String(length=512), nullable=False),
        sa.Column("source_entity_type", sa.String(length=255), nullable=True),
        sa.Column("target_entity_name", sa.String(length=512), nullable=False),
        sa.Column("target_entity_normalized_name", sa.String(length=512), nullable=False),
        sa.Column("target_entity_type", sa.String(length=255), nullable=True),
        sa.Column("relationship_type", sa.String(length=255), nullable=False),
        sa.Column("exact_quote", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["source_entity_fact_id"], ["graph_entity_facts.id"]),
        sa.ForeignKeyConstraint(["target_entity_fact_id"], ["graph_entity_facts.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "document_id", "fact_key", name="uq_graph_relationship_facts_run_document_fact"),
    )
    op.create_index(op.f("ix_graph_relationship_facts_document_id"), "graph_relationship_facts", ["document_id"], unique=False)
    op.create_index(op.f("ix_graph_relationship_facts_run_id"), "graph_relationship_facts", ["run_id"], unique=False)
    op.create_index(op.f("ix_graph_relationship_facts_site_id"), "graph_relationship_facts", ["site_id"], unique=False)
    op.create_index(op.f("ix_graph_relationship_facts_source_entity_fact_id"), "graph_relationship_facts", ["source_entity_fact_id"], unique=False)
    op.create_index(op.f("ix_graph_relationship_facts_target_entity_fact_id"), "graph_relationship_facts", ["target_entity_fact_id"], unique=False)
    op.create_index(op.f("ix_graph_relationship_facts_task_attempt_id"), "graph_relationship_facts", ["task_attempt_id"], unique=False)
    op.create_index(op.f("ix_graph_relationship_facts_task_frame_id"), "graph_relationship_facts", ["task_frame_id"], unique=False)
    op.create_index("ix_graph_relationship_facts_site_run", "graph_relationship_facts", ["site_id", "run_id"], unique=False)
    op.create_index("ix_graph_relationship_facts_run_rel_type", "graph_relationship_facts", ["run_id", "relationship_type"], unique=False)
    op.create_index(
        "ix_graph_relationship_facts_run_source_target",
        "graph_relationship_facts",
        ["run_id", "source_entity_normalized_name", "target_entity_normalized_name"],
        unique=False,
    )

    op.create_table(
        "canonical_entities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("canonical_key", sa.String(length=512), nullable=False),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name", sa.String(length=512), nullable=False),
        sa.Column("entity_type", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolution_confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "canonical_key", name="uq_canonical_entities_run_key"),
    )
    op.create_index(op.f("ix_canonical_entities_run_id"), "canonical_entities", ["run_id"], unique=False)
    op.create_index(op.f("ix_canonical_entities_site_id"), "canonical_entities", ["site_id"], unique=False)
    op.create_index(op.f("ix_canonical_entities_task_attempt_id"), "canonical_entities", ["task_attempt_id"], unique=False)
    op.create_index(op.f("ix_canonical_entities_task_frame_id"), "canonical_entities", ["task_frame_id"], unique=False)
    op.create_index("ix_canonical_entities_site_run", "canonical_entities", ["site_id", "run_id"], unique=False)
    op.create_index("ix_canonical_entities_run_normalized_name", "canonical_entities", ["run_id", "normalized_name"], unique=False)

    op.create_table(
        "canonical_entity_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("canonical_entity_id", sa.UUID(), nullable=False),
        sa.Column("graph_entity_fact_id", sa.UUID(), nullable=False),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["canonical_entity_id"], ["canonical_entities.id"]),
        sa.ForeignKeyConstraint(["graph_entity_fact_id"], ["graph_entity_facts.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "graph_entity_fact_id", name="uq_canonical_entity_memberships_run_fact"),
    )
    op.create_index(op.f("ix_canonical_entity_memberships_canonical_entity_id"), "canonical_entity_memberships", ["canonical_entity_id"], unique=False)
    op.create_index(op.f("ix_canonical_entity_memberships_graph_entity_fact_id"), "canonical_entity_memberships", ["graph_entity_fact_id"], unique=False)
    op.create_index(op.f("ix_canonical_entity_memberships_run_id"), "canonical_entity_memberships", ["run_id"], unique=False)
    op.create_index(op.f("ix_canonical_entity_memberships_site_id"), "canonical_entity_memberships", ["site_id"], unique=False)
    op.create_index(op.f("ix_canonical_entity_memberships_task_attempt_id"), "canonical_entity_memberships", ["task_attempt_id"], unique=False)
    op.create_index(op.f("ix_canonical_entity_memberships_task_frame_id"), "canonical_entity_memberships", ["task_frame_id"], unique=False)
    op.create_index("ix_canonical_entity_memberships_site_run", "canonical_entity_memberships", ["site_id", "run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_canonical_entity_memberships_site_run", table_name="canonical_entity_memberships")
    op.drop_index(op.f("ix_canonical_entity_memberships_task_frame_id"), table_name="canonical_entity_memberships")
    op.drop_index(op.f("ix_canonical_entity_memberships_task_attempt_id"), table_name="canonical_entity_memberships")
    op.drop_index(op.f("ix_canonical_entity_memberships_site_id"), table_name="canonical_entity_memberships")
    op.drop_index(op.f("ix_canonical_entity_memberships_run_id"), table_name="canonical_entity_memberships")
    op.drop_index(op.f("ix_canonical_entity_memberships_graph_entity_fact_id"), table_name="canonical_entity_memberships")
    op.drop_index(op.f("ix_canonical_entity_memberships_canonical_entity_id"), table_name="canonical_entity_memberships")
    op.drop_table("canonical_entity_memberships")

    op.drop_index("ix_canonical_entities_run_normalized_name", table_name="canonical_entities")
    op.drop_index("ix_canonical_entities_site_run", table_name="canonical_entities")
    op.drop_index(op.f("ix_canonical_entities_task_frame_id"), table_name="canonical_entities")
    op.drop_index(op.f("ix_canonical_entities_task_attempt_id"), table_name="canonical_entities")
    op.drop_index(op.f("ix_canonical_entities_site_id"), table_name="canonical_entities")
    op.drop_index(op.f("ix_canonical_entities_run_id"), table_name="canonical_entities")
    op.drop_table("canonical_entities")

    op.drop_index("ix_graph_relationship_facts_run_source_target", table_name="graph_relationship_facts")
    op.drop_index("ix_graph_relationship_facts_run_rel_type", table_name="graph_relationship_facts")
    op.drop_index("ix_graph_relationship_facts_site_run", table_name="graph_relationship_facts")
    op.drop_index(op.f("ix_graph_relationship_facts_task_frame_id"), table_name="graph_relationship_facts")
    op.drop_index(op.f("ix_graph_relationship_facts_task_attempt_id"), table_name="graph_relationship_facts")
    op.drop_index(op.f("ix_graph_relationship_facts_target_entity_fact_id"), table_name="graph_relationship_facts")
    op.drop_index(op.f("ix_graph_relationship_facts_source_entity_fact_id"), table_name="graph_relationship_facts")
    op.drop_index(op.f("ix_graph_relationship_facts_site_id"), table_name="graph_relationship_facts")
    op.drop_index(op.f("ix_graph_relationship_facts_run_id"), table_name="graph_relationship_facts")
    op.drop_index(op.f("ix_graph_relationship_facts_document_id"), table_name="graph_relationship_facts")
    op.drop_table("graph_relationship_facts")

    op.drop_index("ix_graph_entity_facts_run_normalized_name", table_name="graph_entity_facts")
    op.drop_index("ix_graph_entity_facts_run_entity_type", table_name="graph_entity_facts")
    op.drop_index("ix_graph_entity_facts_site_run", table_name="graph_entity_facts")
    op.drop_index(op.f("ix_graph_entity_facts_task_frame_id"), table_name="graph_entity_facts")
    op.drop_index(op.f("ix_graph_entity_facts_task_attempt_id"), table_name="graph_entity_facts")
    op.drop_index(op.f("ix_graph_entity_facts_site_id"), table_name="graph_entity_facts")
    op.drop_index(op.f("ix_graph_entity_facts_run_id"), table_name="graph_entity_facts")
    op.drop_index(op.f("ix_graph_entity_facts_document_id"), table_name="graph_entity_facts")
    op.drop_table("graph_entity_facts")
