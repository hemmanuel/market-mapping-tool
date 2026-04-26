"""add normalized company enrichment tables

Revision ID: 3f2e4a1c9b70
Revises: e6f1c2a7b9d3
Create Date: 2026-04-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3f2e4a1c9b70"
down_revision: Union[str, Sequence[str], None] = "e6f1c2a7b9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_enrichment_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("company_name", sa.String(length=512), nullable=False),
        sa.Column("normalized_company_name", sa.String(length=512), nullable=False),
        sa.Column("legal_name", sa.String(length=512), nullable=True),
        sa.Column("primary_url", sa.String(length=2048), nullable=True),
        sa.Column("full_description", sa.Text(), nullable=True),
        sa.Column("pitch_summary", sa.Text(), nullable=True),
        sa.Column("primary_sector", sa.String(length=255), nullable=True),
        sa.Column("business_model", sa.String(length=255), nullable=True),
        sa.Column("customer_type", sa.String(length=255), nullable=True),
        sa.Column("investment_thesis_one_liner", sa.Text(), nullable=True),
        sa.Column("tangibility_score", sa.Integer(), nullable=True),
        sa.Column("venture_scale_score", sa.Float(), nullable=True),
        sa.Column("stage_estimate", sa.String(length=255), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("company_twitter_url", sa.String(length=2048), nullable=True),
        sa.Column("taxonomy_l1", sa.String(length=255), nullable=True),
        sa.Column("taxonomy_l2", sa.String(length=255), nullable=True),
        sa.Column("taxonomy_l3", sa.String(length=255), nullable=True),
        sa.Column("tech_stack_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("dimension_scores_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("vc_dossier_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("strategic_analysis_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metric_rationales_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_document_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_urls_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "normalized_company_name", name="uq_company_enrichment_profiles_site_company"),
    )
    op.create_index(
        "ix_company_enrichment_profiles_site_stage",
        "company_enrichment_profiles",
        ["site_id", "stage_estimate"],
        unique=False,
    )
    op.create_index(
        "ix_company_enrichment_profiles_site_sector",
        "company_enrichment_profiles",
        ["site_id", "primary_sector"],
        unique=False,
    )

    op.create_table(
        "company_enrichment_founders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("task_frame_id", sa.UUID(), nullable=False),
        sa.Column("task_attempt_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("hometown", sa.String(length=255), nullable=True),
        sa.Column("linkedin_url", sa.String(length=2048), nullable=True),
        sa.Column("twitter_url", sa.String(length=2048), nullable=True),
        sa.Column("previous_companies_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("education_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_technical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["company_enrichment_profiles.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["task_frame_id"], ["orchestration_task_frames.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "name", "role", name="uq_company_enrichment_founders_profile_name_role"),
    )
    op.create_index(
        "ix_company_enrichment_founders_site_profile",
        "company_enrichment_founders",
        ["site_id", "profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_company_enrichment_founders_site_profile", table_name="company_enrichment_founders")
    op.drop_table("company_enrichment_founders")
    op.drop_index("ix_company_enrichment_profiles_site_sector", table_name="company_enrichment_profiles")
    op.drop_index("ix_company_enrichment_profiles_site_stage", table_name="company_enrichment_profiles")
    op.drop_table("company_enrichment_profiles")
