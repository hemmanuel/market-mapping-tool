import re
import uuid

from sqlalchemy import delete, select, text

from src.agents.neo4j_enrichment import project_company_enrichment_to_neo4j
from src.agents.schemas.enrichment import CompanyEnrichment
from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.orchestrator.core.enrichment_models import CompanyEnrichmentFounder, CompanyEnrichmentProfile
from src.orchestrator.core.schemas import (
    PersistCompanyEnrichmentInput,
    PersistCompanyEnrichmentOutput,
    ProjectCompanyEnrichmentInput,
    ProjectCompanyEnrichmentOutput,
    TaskFrame,
)


def normalize_company_name(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return re.sub(r"\s+", " ", lowered).strip()


async def enrichment_tables_ready() -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    to_regclass('public.company_enrichment_profiles') AS profiles,
                    to_regclass('public.company_enrichment_founders') AS founders
                """
            )
        )
        row = result.one()
        return bool(row.profiles and row.founders)


class PersistCompanyEnrichmentWorker:
    accepts_attempt_id = True

    async def execute(self, task: TaskFrame, attempt_id: str) -> PersistCompanyEnrichmentOutput:
        payload = PersistCompanyEnrichmentInput(**task.payload)
        pipeline_id = task.pipeline_id

        if not await enrichment_tables_ready():
            await event_manager.publish(
                pipeline_id,
                {
                    "type": "log",
                    "message": (
                        "[EnrichmentPersistence] Normalized enrichment tables are not available yet. "
                        "Skipping relational persistence until migrations are applied."
                    ),
                },
            )
            return PersistCompanyEnrichmentOutput(
                persisted=False,
                company_name=payload.company_name,
            )

        profile = CompanyEnrichment(**payload.company_profile)
        company_key = normalize_company_name(profile.company_name or profile.name)
        source_urls = list(dict.fromkeys(list(payload.source_urls) + list(profile.vc_dossier.source_urls)))

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CompanyEnrichmentProfile)
                .where(
                    CompanyEnrichmentProfile.site_id == uuid.UUID(pipeline_id),
                    CompanyEnrichmentProfile.normalized_company_name == company_key,
                )
                .limit(1)
            )
            record = result.scalars().first()
            if not record:
                record = CompanyEnrichmentProfile(
                    site_id=uuid.UUID(pipeline_id),
                    run_id=uuid.UUID(task.run_id),
                    task_frame_id=uuid.UUID(task.task_id),
                    task_attempt_id=uuid.UUID(attempt_id),
                    company_name=profile.company_name,
                    normalized_company_name=company_key,
                )
                session.add(record)

            record.run_id = uuid.UUID(task.run_id)
            record.task_frame_id = uuid.UUID(task.task_id)
            record.task_attempt_id = uuid.UUID(attempt_id)
            record.company_name = profile.company_name
            record.normalized_company_name = company_key
            record.legal_name = profile.name
            record.primary_url = profile.url
            record.full_description = profile.full_description
            record.pitch_summary = profile.pitch_summary
            record.primary_sector = profile.primary_sector
            record.business_model = profile.business_model
            record.customer_type = profile.customer_type
            record.investment_thesis_one_liner = profile.investment_thesis_one_liner
            record.tangibility_score = profile.tangibility_score
            record.venture_scale_score = profile.venture_scale_score
            record.stage_estimate = profile.stage_estimate
            record.rationale = profile.rationale
            record.company_twitter_url = profile.company_twitter_url
            record.taxonomy_l1 = profile.taxonomy.l1
            record.taxonomy_l2 = profile.taxonomy.l2
            record.taxonomy_l3 = profile.taxonomy.l3
            record.tech_stack_json = list(profile.tech_stack)
            record.dimension_scores_json = dict(profile.dimension_scores)
            record.vc_dossier_json = profile.vc_dossier.model_dump()
            record.strategic_analysis_json = profile.strategic_analysis.model_dump()
            record.metric_rationales_json = profile.metric_rationales.model_dump()
            record.source_document_ids_json = list(payload.source_document_ids)
            record.source_urls_json = source_urls
            record.metadata_json = {
                "niche": payload.niche,
                "founder_count": len(profile.founders),
                "source_document_ids": payload.source_document_ids,
            }
            record.status = "active"

            await session.flush()
            await session.execute(
                delete(CompanyEnrichmentFounder).where(CompanyEnrichmentFounder.profile_id == record.id)
            )

            founder_ids: list[str] = []
            for founder in profile.founders:
                founder_record = CompanyEnrichmentFounder(
                    profile_id=record.id,
                    site_id=uuid.UUID(pipeline_id),
                    run_id=uuid.UUID(task.run_id),
                    task_frame_id=uuid.UUID(task.task_id),
                    task_attempt_id=uuid.UUID(attempt_id),
                    name=founder.name,
                    role=founder.role,
                    bio=founder.bio,
                    hometown=founder.hometown,
                    linkedin_url=founder.linkedin_url,
                    twitter_url=founder.twitter_url,
                    previous_companies_json=list(founder.previous_companies),
                    education_json=list(founder.education),
                    is_technical=founder.is_technical,
                    tags_json=list(founder.tags),
                    metadata_json={},
                )
                session.add(founder_record)
                await session.flush()
                founder_ids.append(str(founder_record.id))

            await session.commit()

        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": (
                    f"[EnrichmentPersistence] Persisted normalized enrichment for {record.company_name} "
                    f"with {len(founder_ids)} founder row(s)."
                ),
            },
        )
        return PersistCompanyEnrichmentOutput(
            persisted=True,
            company_enrichment_id=str(record.id),
            founder_ids=founder_ids,
            company_name=record.company_name,
        )


class ProjectCompanyEnrichmentWorker:
    async def execute(self, task: TaskFrame) -> ProjectCompanyEnrichmentOutput:
        payload = ProjectCompanyEnrichmentInput(**task.payload)
        pipeline_id = task.pipeline_id

        if not await enrichment_tables_ready():
            await event_manager.publish(
                pipeline_id,
                {
                    "type": "log",
                    "message": "[EnrichmentProjection] Skipping projection because normalized tables are unavailable.",
                },
            )
            return ProjectCompanyEnrichmentOutput(projected=False)

        async with AsyncSessionLocal() as session:
            record = await session.get(CompanyEnrichmentProfile, uuid.UUID(payload.company_enrichment_id))
            if not record:
                await event_manager.publish(
                    pipeline_id,
                    {
                        "type": "log",
                        "message": (
                            f"[EnrichmentProjection] Skipping projection because company enrichment "
                            f"{payload.company_enrichment_id} was not found."
                        ),
                    },
                )
                return ProjectCompanyEnrichmentOutput(projected=False)

            founder_result = await session.execute(
                select(CompanyEnrichmentFounder)
                .where(CompanyEnrichmentFounder.profile_id == record.id)
                .order_by(CompanyEnrichmentFounder.created_at)
            )
            founders = founder_result.scalars().all()

            company_payload = {
                "name": record.legal_name or record.company_name,
                "company_name": record.company_name,
                "url": record.primary_url or "",
                "full_description": record.full_description or "",
                "pitch_summary": record.pitch_summary or "",
                "primary_sector": record.primary_sector or "",
                "business_model": record.business_model or "",
                "tech_stack": list(record.tech_stack_json or []),
                "tangibility_score": record.tangibility_score or 0,
                "customer_type": record.customer_type or "",
                "investment_thesis_one_liner": record.investment_thesis_one_liner or "",
                "dimension_scores": dict(record.dimension_scores_json or {}),
                "venture_scale_score": record.venture_scale_score or 0.0,
                "stage_estimate": record.stage_estimate or "",
                "rationale": record.rationale or "",
                "taxonomy": {
                    "l1": record.taxonomy_l1 or "",
                    "l2": record.taxonomy_l2 or "",
                    "l3": record.taxonomy_l3 or "",
                },
                "vc_dossier": dict(record.vc_dossier_json or {}),
                "founders": [
                    {
                        "name": founder.name,
                        "role": founder.role or "",
                        "bio": founder.bio or "",
                        "hometown": founder.hometown,
                        "linkedin_url": founder.linkedin_url,
                        "twitter_url": founder.twitter_url,
                        "previous_companies": list(founder.previous_companies_json or []),
                        "education": list(founder.education_json or []),
                        "is_technical": founder.is_technical,
                        "tags": list(founder.tags_json or []),
                    }
                    for founder in founders
                ],
                "company_twitter_url": record.company_twitter_url,
                "strategic_analysis": dict(record.strategic_analysis_json or {}),
                "metric_rationales": dict(record.metric_rationales_json or {}),
                "source_document_ids": list(record.source_document_ids_json or []),
                "source_urls": list(record.source_urls_json or []),
            }

        await project_company_enrichment_to_neo4j(pipeline_id, company_payload)
        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": f"[EnrichmentProjection] Projected normalized enrichment for {record.company_name} to Neo4j.",
            },
        )
        return ProjectCompanyEnrichmentOutput(
            projected=True,
            projected_companies=1,
            projected_founders=len(founders),
            company_name=record.company_name,
        )
