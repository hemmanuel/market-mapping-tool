import uuid

from sqlalchemy import select

from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.models.relational import DataSource, Document as PGDocument
from src.orchestrator.core.graph_contracts import (
    GraphFactExtractionInput,
    GraphFactExtractionOutput,
    GraphFactExtractionPersistResult,
)
from src.orchestrator.core.graph_store import persist_graph_fact_extraction
from src.orchestrator.core.llm import BespokeLLMClient
from src.orchestrator.core.schemas import TaskFrame


class GraphFactExtractionWorker:
    accepts_attempt_id = True

    def __init__(self, llm_client: BespokeLLMClient):
        self.llm_client = llm_client

    async def execute(self, task: TaskFrame, attempt_id: str | None = None) -> GraphFactExtractionPersistResult:
        if not attempt_id:
            raise RuntimeError("GraphFactExtractionWorker requires a task attempt id for durable lineage.")

        payload = GraphFactExtractionInput(**task.payload)
        pipeline_id = task.pipeline_id
        document_uuid = uuid.UUID(payload.document.document_id)
        site_uuid = uuid.UUID(payload.site_id)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PGDocument)
                .join(DataSource, PGDocument.data_source_id == DataSource.id)
                .where(PGDocument.id == document_uuid, DataSource.site_id == site_uuid)
            )
            document = result.scalars().first()
            if document is None:
                raise RuntimeError(f"Document {payload.document.document_id} not found for graph extraction.")

            metadata = document.metadata_json if isinstance(document.metadata_json, dict) else {}
            source_url = payload.document.source_url or metadata.get("source_url")
            raw_text = payload.raw_text or document.raw_text
            if not raw_text:
                await event_manager.publish(
                    pipeline_id,
                    {
                        "type": "log",
                        "message": f"[GraphFactExtraction] Skipped empty document chunk {payload.document.document_id}.",
                    },
                )
                return GraphFactExtractionPersistResult(
                    document_id=payload.document.document_id,
                    entity_fact_ids=[],
                    relationship_fact_ids=[],
                )

            await event_manager.publish(
                pipeline_id,
                {
                    "type": "log",
                    "message": f"[GraphFactExtraction] Extracting graph facts from chunk {payload.document.document_id}.",
                },
            )

            entity_hints = ", ".join(payload.schema_entities) if payload.schema_entities else "None"
            relationship_hints = (
                ", ".join(hint.to_prompt_hint() for hint in payload.schema_relationships)
                if payload.schema_relationships
                else "None"
            )
            prompt = f"""You are a market-intelligence graph extraction system.

You are reading a single PostgreSQL document chunk that came through the front-door ingestion path.
Extract real-world entities and explicit relationships that are supported by this chunk.

Rules:
- Ignore page furniture, navigation chrome, and generic boilerplate unless it contains meaningful market evidence.
- Prefer real companies, investors, products, technologies, regulations, agencies, people, facilities, metrics, and concepts.
- For every entity, populate:
  - `entity_name`
  - `entity_type`
  - `description`: concise context grounded in the chunk
  - `evidence_text`: a short verbatim substring supporting the mention when available
- For every relationship, populate:
  - `source_entity_name`
  - `target_entity_name`
  - `relationship_type`
  - `exact_quote`: an exact verbatim substring that proves the relationship
- Do not invent facts.
- The ontology hints are guidance, not constraints.

Niche: {payload.niche or "Unknown"}
Entity hints: {entity_hints}
Relationship hints: {relationship_hints}
Document title: {payload.document.title or document.title or "Unknown"}
Source URL: {source_url or "Unknown"}
Chunk index: {payload.document.chunk_index if payload.document.chunk_index is not None else metadata.get("chunk_index", "Unknown")}

Chunk text:
{raw_text}
"""

            extracted = await self.llm_client.generate_structured(
                prompt=prompt,
                response_schema=GraphFactExtractionOutput,
            )

            persisted = await persist_graph_fact_extraction(
                session,
                run_id=payload.run_id,
                site_id=payload.site_id,
                document_id=payload.document.document_id,
                task_frame_id=task.task_id,
                task_attempt_id=attempt_id,
                source_url=source_url,
                output=extracted,
            )
            await session.commit()

        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": (
                    "[GraphFactExtraction] Persisted "
                    f"{len(persisted.entity_fact_ids)} entity fact(s) and "
                    f"{len(persisted.relationship_fact_ids)} relationship fact(s) "
                    f"for chunk {payload.document.document_id}."
                ),
            },
        )

        return GraphFactExtractionPersistResult(
            document_id=payload.document.document_id,
            entity_fact_ids=persisted.entity_fact_ids,
            relationship_fact_ids=persisted.relationship_fact_ids,
        )
