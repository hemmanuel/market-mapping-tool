"""add canonical relationships table

Revision ID: c4f2d8b1a7e6
Revises: b3d4a9e1c2f7
Create Date: 2026-04-23 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4f2d8b1a7e6"
down_revision: Union[str, Sequence[str], None] = "b3d4a9e1c2f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canonical_relationships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("source_canonical_entity_id", sa.UUID(), nullable=False),
        sa.Column("target_canonical_entity_id", sa.UUID(), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("canonical_relationship_key", sa.String(length=512), nullable=False),
        sa.Column("source_canonical_key", sa.String(length=512), nullable=False),
        sa.Column("target_canonical_key", sa.String(length=512), nullable=False),
        sa.Column("relationship_type", sa.String(length=255), nullable=False),
        sa.Column("normalized_relationship_type", sa.String(length=255), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("quotes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_urls_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supporting_fact_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.ForeignKeyConstraint(["source_canonical_entity_id"], ["canonical_entities.id"]),
        sa.ForeignKeyConstraint(["target_canonical_entity_id"], ["canonical_entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "canonical_relationship_key", name="uq_canonical_relationships_run_key"),
    )
    op.create_index(op.f("ix_canonical_relationships_run_id"), "canonical_relationships", ["run_id"], unique=False)
    op.create_index(op.f("ix_canonical_relationships_site_id"), "canonical_relationships", ["site_id"], unique=False)
    op.create_index(op.f("ix_canonical_relationships_task_frame_id"), "canonical_relationships", ["task_frame_id"], unique=False)
    op.create_index(op.f("ix_canonical_relationships_task_attempt_id"), "canonical_relationships", ["task_attempt_id"], unique=False)
    op.create_index(
        op.f("ix_canonical_relationships_source_canonical_entity_id"),
        "canonical_relationships",
        ["source_canonical_entity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_canonical_relationships_target_canonical_entity_id"),
        "canonical_relationships",
        ["target_canonical_entity_id"],
        unique=False,
    )
    op.create_index("ix_canonical_relationships_site_run", "canonical_relationships", ["site_id", "run_id"], unique=False)
    op.create_index("ix_canonical_relationships_run_rel_type", "canonical_relationships", ["run_id", "relationship_type"], unique=False)
    op.create_index(
        "ix_canonical_relationships_run_source_target",
        "canonical_relationships",
        ["run_id", "source_canonical_key", "target_canonical_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_canonical_relationships_run_source_target", table_name="canonical_relationships")
    op.drop_index("ix_canonical_relationships_run_rel_type", table_name="canonical_relationships")
    op.drop_index("ix_canonical_relationships_site_run", table_name="canonical_relationships")
    op.drop_index(op.f("ix_canonical_relationships_target_canonical_entity_id"), table_name="canonical_relationships")
    op.drop_index(op.f("ix_canonical_relationships_source_canonical_entity_id"), table_name="canonical_relationships")
    op.drop_index(op.f("ix_canonical_relationships_task_attempt_id"), table_name="canonical_relationships")
    op.drop_index(op.f("ix_canonical_relationships_task_frame_id"), table_name="canonical_relationships")
    op.drop_index(op.f("ix_canonical_relationships_site_id"), table_name="canonical_relationships")
    op.drop_index(op.f("ix_canonical_relationships_run_id"), table_name="canonical_relationships")
    op.drop_table("canonical_relationships")
