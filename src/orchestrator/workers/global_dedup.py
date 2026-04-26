from sqlalchemy import Integer
from sqlalchemy.future import select

from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.models.relational import DataSource, Document as PGDocument
from src.orchestrator.core.schemas import GlobalDedupInput, GlobalDedupOutput, TaskFrame


class GlobalDedupWorker:
    async def execute(self, task: TaskFrame) -> GlobalDedupOutput:
        payload = GlobalDedupInput(**task.payload)
        pipeline_id = task.pipeline_id
        url = payload.url
        company_name = payload.company_name

        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[GlobalDedup] Checking cache for {url}..."})

        async with AsyncSessionLocal() as session:
            current_site_docs_result = await session.execute(
                select(PGDocument)
                .join(DataSource, PGDocument.data_source_id == DataSource.id)
                .where(
                    DataSource.site_id == pipeline_id,
                    PGDocument.metadata_json["source_url"].astext == url,
                )
            )
            current_site_docs = current_site_docs_result.scalars().all()
            if current_site_docs:
                metadata_updated = False
                for doc in current_site_docs:
                    metadata_json = dict(doc.metadata_json or {})
                    company_names = list(metadata_json.get("company_names") or [])
                    if company_name and company_name not in company_names:
                        company_names.append(company_name)
                        metadata_updated = True
                    if company_name and not metadata_json.get("company_name"):
                        metadata_json["company_name"] = company_name
                        metadata_updated = True
                    if company_names:
                        metadata_json["company_names"] = company_names
                    doc.metadata_json = metadata_json
                if metadata_updated:
                    await session.commit()
                await event_manager.publish(
                    pipeline_id,
                    {"type": "log", "message": f"[GlobalDedup] Source already exists on this site: {url}"},
                )
                return GlobalDedupOutput(url=url, should_enqueue_scrape=False, cached_chunk_count=0)

            existing_docs_result = await session.execute(
                select(PGDocument)
                .where(PGDocument.metadata_json["source_url"].astext == url)
                .order_by(PGDocument.metadata_json["chunk_index"].astext.cast(Integer))
            )
            existing_docs = existing_docs_result.scalars().all()

            if not existing_docs:
                await event_manager.publish(
                    pipeline_id,
                    {"type": "log", "message": f"[GlobalDedup] Cache miss for {url}. Scheduling scrape."},
                )
                return GlobalDedupOutput(url=url, should_enqueue_scrape=True, cached_chunk_count=0)

            data_source_result = await session.execute(select(DataSource).where(DataSource.site_id == pipeline_id).limit(1))
            data_source = data_source_result.scalars().first()
            if not data_source:
                data_source = DataSource(
                    site_id=pipeline_id,
                    source_type="web_search",
                    name="Autonomous Web Search",
                    config={},
                )
                session.add(data_source)
                await session.flush()

            stored_chunks = 0
            for doc in existing_docs:
                metadata_json = dict(doc.metadata_json or {})
                company_names = list(metadata_json.get("company_names") or [])
                if company_name and company_name not in company_names:
                    company_names.append(company_name)
                if company_name:
                    metadata_json["company_name"] = metadata_json.get("company_name") or company_name
                    metadata_json["company_names"] = company_names
                session.add(
                    PGDocument(
                        data_source_id=data_source.id,
                        title=doc.title,
                        raw_text=doc.raw_text,
                        embedding=doc.embedding,
                        metadata_json=metadata_json,
                    )
                )
                stored_chunks += 1

            await session.commit()
            await event_manager.publish(
                pipeline_id,
                {"type": "log", "message": f"[GlobalDedup] Cloned {stored_chunks} cached chunks for {url}."},
            )
            return GlobalDedupOutput(url=url, should_enqueue_scrape=False, cached_chunk_count=stored_chunks)
