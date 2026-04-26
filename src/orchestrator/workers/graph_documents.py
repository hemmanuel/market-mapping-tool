import uuid

from sqlalchemy import select

from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.models.relational import DataSource, Document as PGDocument
from src.orchestrator.core.graph_contracts import (
    GraphDocumentReference,
    GraphDocumentSelectionInput,
    GraphDocumentSelectionOutput,
)
from src.orchestrator.core.schemas import TaskFrame


class GraphDocumentSelectionWorker:
    async def execute(self, task: TaskFrame) -> GraphDocumentSelectionOutput:
        payload = GraphDocumentSelectionInput(**task.payload)
        pipeline_id = task.pipeline_id

        ordered_document_ids: list[str] = []
        seen: set[str] = set()
        for document_id in payload.candidate_document_ids:
            if document_id in seen:
                continue
            seen.add(document_id)
            ordered_document_ids.append(document_id)

        site_uuid = uuid.UUID(payload.site_id)
        async with AsyncSessionLocal() as session:
            if ordered_document_ids:
                document_uuids = [uuid.UUID(document_id) for document_id in ordered_document_ids]
                result = await session.execute(
                    select(PGDocument)
                    .join(DataSource, PGDocument.data_source_id == DataSource.id)
                    .where(PGDocument.id.in_(document_uuids), DataSource.site_id == site_uuid)
                )
                documents = result.scalars().all()
            else:
                result = await session.execute(
                    select(PGDocument)
                    .join(DataSource, PGDocument.data_source_id == DataSource.id)
                    .where(DataSource.site_id == site_uuid)
                    .order_by(PGDocument.processed_at.asc(), PGDocument.id.asc())
                )
                documents = result.scalars().all()
                ordered_document_ids = [str(document.id) for document in documents]

        documents_by_id = {str(document.id): document for document in documents}
        references: list[GraphDocumentReference] = []
        for document_id in ordered_document_ids:
            document = documents_by_id.get(document_id)
            if document is None:
                continue

            metadata = document.metadata_json if isinstance(document.metadata_json, dict) else {}
            references.append(
                GraphDocumentReference(
                    document_id=str(document.id),
                    title=document.title,
                    source_url=metadata.get("source_url"),
                    chunk_index=metadata.get("chunk_index"),
                )
            )

        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": (
                    f"[GraphDocumentSelection] Selected {len(references)} document chunk(s) for graph extraction."
                    if payload.candidate_document_ids
                    else f"[GraphDocumentSelection] Selected all {len(references)} stored document chunk(s) for graph extraction."
                ),
            },
        )
        return GraphDocumentSelectionOutput(documents=references)
