import uuid
from collections import defaultdict

from sqlalchemy import Integer, or_, select, text

from src.agents.enrichment_agent import extract_enrichment_source_urls, synthesize_company_enrichment
from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.models.relational import DataSource, Document as PGDocument
from src.orchestrator.core.ledger_models import OrchestrationTaskFrameRecord
from src.orchestrator.core.schemas import EnrichCompanyInput, EnrichCompanyOutput, TaskFrame

SOURCE_TASK_TYPES = {
    "PLAN_COMPANY_SEARCH",
    "SEARCH_QUERY",
    "GLOBAL_DEDUP_URL",
    "SCRAPE_URL",
    "BOUNCER_EVALUATION",
    "VECTOR_STORAGE",
}

MAX_EVIDENCE_URLS = 8
MAX_CHUNKS_PER_URL = 3


class EnrichmentWorker:
    async def execute(self, task: TaskFrame) -> EnrichCompanyOutput:
        payload = EnrichCompanyInput(**task.payload)
        company_name = payload.company_name
        niche = payload.niche
        pipeline_id = task.pipeline_id

        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": f"[Enrichment] Checking front-door evidence for {company_name}.",
            },
        )

        try:
            pending_source_tasks = await self._count_pending_source_tasks(task.run_id, company_name)
            evidence_records = await self._load_evidence_records(pipeline_id, company_name)
            source_urls = extract_enrichment_source_urls(evidence_records)
            source_document_ids = [record["document_id"] for record in evidence_records]

            if pending_source_tasks > 0:
                next_poll = payload.poll_count + 1
                await event_manager.publish(
                    pipeline_id,
                    {
                        "type": "log",
                        "message": (
                            f"[Enrichment] Waiting for front-door acquisition for {company_name} "
                            f"({pending_source_tasks} source task(s) pending, poll {next_poll})."
                        ),
                    },
                )
                return EnrichCompanyOutput(
                    company_profile={},
                    status="WAITING",
                    poll_count=next_poll,
                    document_count=len(evidence_records),
                    pending_source_tasks=pending_source_tasks,
                    source_document_ids=source_document_ids,
                    source_urls=source_urls,
                )

            if not evidence_records:
                await event_manager.publish(
                    pipeline_id,
                    {
                        "type": "log",
                        "message": (
                            f"[Enrichment] No persisted evidence was found for {company_name} "
                            "after front-door acquisition completed."
                        ),
                    },
                )
                return EnrichCompanyOutput(
                    company_profile={},
                    status="NO_EVIDENCE",
                    poll_count=payload.poll_count,
                    document_count=0,
                    pending_source_tasks=0,
                    source_document_ids=[],
                    source_urls=[],
                )

            await event_manager.publish(
                pipeline_id,
                {
                    "type": "log",
                    "message": (
                        f"[Enrichment] Synthesizing dossier for {company_name} from "
                        f"{len(evidence_records)} stored chunk(s) across {len(source_urls)} source URL(s)."
                    ),
                },
            )
            enriched = await synthesize_company_enrichment(company_name, niche, evidence_records)
            return EnrichCompanyOutput(
                company_profile=enriched.model_dump(),
                status="SUCCESS",
                poll_count=payload.poll_count,
                document_count=len(evidence_records),
                pending_source_tasks=0,
                source_document_ids=source_document_ids,
                source_urls=source_urls,
            )
        except Exception as exc:
            await event_manager.publish(
                pipeline_id,
                {
                    "type": "log",
                    "message": f"[Enrichment] Error enriching {company_name}: {exc}",
                },
            )
            raise

    async def _count_pending_source_tasks(self, run_id: str | None, company_name: str) -> int:
        if not run_id:
            return 0

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OrchestrationTaskFrameRecord.status)
                .where(
                    OrchestrationTaskFrameRecord.run_id == uuid.UUID(run_id),
                    OrchestrationTaskFrameRecord.partition_key == company_name,
                    OrchestrationTaskFrameRecord.task_type.in_(SOURCE_TASK_TYPES),
                )
            )
            return sum(1 for status in result.scalars().all() if status in {"pending", "in_progress"})

    async def _load_evidence_records(self, pipeline_id: str, company_name: str) -> list[dict[str, str]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PGDocument)
                .join(DataSource, PGDocument.data_source_id == DataSource.id)
                .where(
                    DataSource.site_id == pipeline_id,
                    or_(
                        PGDocument.metadata_json["company_name"].astext == company_name,
                        text("(documents.metadata_json -> 'company_names') ? :company_name"),
                    ),
                )
                .order_by(
                    PGDocument.processed_at.desc(),
                    PGDocument.metadata_json["source_url"].astext,
                    PGDocument.metadata_json["chunk_index"].astext.cast(Integer),
                )
                .params(company_name=company_name)
            )
            documents = result.scalars().all()

        selected_records: list[dict[str, str]] = []
        chunks_by_url: defaultdict[str, int] = defaultdict(int)
        seen_urls: list[str] = []

        for document in documents:
            metadata_json = document.metadata_json or {}
            source_url = str(metadata_json.get("source_url") or f"document:{document.id}")
            if source_url not in seen_urls:
                if len(seen_urls) >= MAX_EVIDENCE_URLS:
                    continue
                seen_urls.append(source_url)
            if chunks_by_url[source_url] >= MAX_CHUNKS_PER_URL:
                continue

            chunks_by_url[source_url] += 1
            selected_records.append(
                {
                    "document_id": str(document.id),
                    "title": document.title or "",
                    "source_url": source_url,
                    "raw_text": document.raw_text,
                    "storage_object": str(metadata_json.get("storage_object") or ""),
                }
            )

        return selected_records
