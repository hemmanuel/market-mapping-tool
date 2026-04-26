"""add canonical community tables

Revision ID: e6f1c2a7b9d3
Revises: c4f2d8b1a7e6
Create Date: 2026-04-23 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e6f1c2a7b9d3"
down_revision: Union[str, Sequence[str], None] = "c4f2d8b1a7e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canonical_communities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("schema_version", sa.String(length=50), nullable=False),
        sa.Column("community_key", sa.String(length=512), nullable=False),
        sa.Column("algorithm", sa.String(length=100), nullable=False),
        sa.Column("algorithm_version", sa.String(length=100), nullable=False),
        sa.Column("community_name", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("relationship_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "community_key", name="uq_canonical_communities_run_key"),
    )
    op.create_index(op.f("ix_canonical_communities_run_id"), "canonical_communities", ["run_id"], unique=False)
    op.create_index(op.f("ix_canonical_communities_site_id"), "canonical_communities", ["site_id"], unique=False)
    op.create_index(op.f("ix_canonical_communities_task_frame_id"), "canonical_communities", ["task_frame_id"], unique=False)
    op.create_index(op.f("ix_canonical_communities_task_attempt_id"), "canonical_communities", ["task_attempt_id"], unique=False)
    op.create_index("ix_canonical_communities_site_run", "canonical_communities", ["site_id", "run_id"], unique=False)
    op.create_index("ix_canonical_communities_run_algorithm", "canonical_communities", ["run_id", "algorithm"], unique=False)

    op.create_table(
        "canonical_community_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("canonical_community_id", sa.UUID(), nullable=False),
        sa.Column("canonical_entity_id", sa.UUID(), nullable=False),
        sa.Column("membership_rank", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.ForeignKeyConstraint(["canonical_community_id"], ["canonical_communities.id"]),
        sa.ForeignKeyConstraint(["canonical_entity_id"], ["canonical_entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "canonical_entity_id", name="uq_canonical_community_memberships_run_entity"),
    )
    op.create_index(
        op.f("ix_canonical_community_memberships_run_id"),
        "canonical_community_memberships",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_canonical_community_memberships_site_id"),
        "canonical_community_memberships",
        ["site_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_canonical_community_memberships_task_frame_id"),
        "canonical_community_memberships",
        ["task_frame_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_canonical_community_memberships_task_attempt_id"),
        "canonical_community_memberships",
        ["task_attempt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_canonical_community_memberships_canonical_community_id"),
        "canonical_community_memberships",
        ["canonical_community_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_canonical_community_memberships_canonical_entity_id"),
        "canonical_community_memberships",
        ["canonical_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_canonical_community_memberships_site_run",
        "canonical_community_memberships",
        ["site_id", "run_id"],
        unique=False,
    )
def downgrade() -> None:
    op.drop_index("ix_canonical_community_memberships_site_run", table_name="canonical_community_memberships")
    op.drop_index(
        op.f("ix_canonical_community_memberships_canonical_entity_id"),
        table_name="canonical_community_memberships",
    )
    op.drop_index(
        op.f("ix_canonical_community_memberships_canonical_community_id"),
        table_name="canonical_community_memberships",
    )
    op.drop_index(op.f("ix_canonical_community_memberships_task_attempt_id"), table_name="canonical_community_memberships")
    op.drop_index(op.f("ix_canonical_community_memberships_task_frame_id"), table_name="canonical_community_memberships")
    op.drop_index(op.f("ix_canonical_community_memberships_site_id"), table_name="canonical_community_memberships")
    op.drop_index(op.f("ix_canonical_community_memberships_run_id"), table_name="canonical_community_memberships")
    op.drop_table("canonical_community_memberships")

    op.drop_index("ix_canonical_communities_run_algorithm", table_name="canonical_communities")
    op.drop_index("ix_canonical_communities_site_run", table_name="canonical_communities")
    op.drop_index(op.f("ix_canonical_communities_task_attempt_id"), table_name="canonical_communities")
    op.drop_index(op.f("ix_canonical_communities_task_frame_id"), table_name="canonical_communities")
    op.drop_index(op.f("ix_canonical_communities_site_id"), table_name="canonical_communities")
    op.drop_index(op.f("ix_canonical_communities_run_id"), table_name="canonical_communities")
    op.drop_table("canonical_communities")
