from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
import json
import asyncio
import csv
import io
import zipfile

from src.db.session import AsyncSessionLocal, get_db_session
from src.models.relational import Tenant, Site, DataSource, PendingDocument
from src.api.schemas import PipelineConfig
from src.api.auth import get_current_tenant
from src.api.events import event_manager
from src.orchestrator.core.engine import Orchestrator

router = APIRouter()

# Global registry to track active workflows and their cancellation events
active_workflows: dict[str, asyncio.Event] = {}
active_graph_workflows: dict[str, asyncio.Event] = {}
active_graph_runs: dict[str, str] = {}

# Global orchestrator instance
orchestrator = Orchestrator()

async def run_acquisition_workflow(site_id: str, niche: str, ontology: dict, cancel_event: asyncio.Event):
    try:
        await event_manager.publish(site_id, {"type": "log", "message": f"Starting acquisition for niche: {niche}"})
        
        # Start the pipeline using the new Orchestrator
        run_id = await orchestrator.start_pipeline(
            pipeline_id=site_id,
            initial_task_type="MARKET_SIZING",
            payload={
                "niche": niche,
                "schema_entities": ontology.get("entities", []),
                "schema_relationships": ontology.get("relationships", [])
            }
        )
        
        final_status = await orchestrator.wait_for_run(run_id, cancel_event=cancel_event)
        await event_manager.publish(site_id, {"type": "log", "message": f"Workflow finished with status: {final_status}"})
            
    except Exception as e:
        await event_manager.publish(site_id, {"type": "log", "message": f"Workflow failed: {str(e)}"})
        print(f"Workflow failed: {e}")
    finally:
        active_workflows.pop(site_id, None)
        await event_manager.publish(site_id, {"type": "status", "is_acquiring": False})


async def _set_site_graph_status(site_id: str, status: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Site).where(Site.id == site_id))
        site = result.scalars().first()
        if site:
            site.graph_status = status
            await session.commit()


def _terminal_graph_status(final_status: str) -> str:
    if final_status == "completed":
        return "ready"
    return final_status


async def run_graph_workflow(site_id: str, niche: str, ontology: dict, cancel_event: asyncio.Event):
    run_id: str | None = None
    try:
        await _set_site_graph_status(site_id, "processing")
        await event_manager.publish(site_id, {"type": "log", "message": "Starting bespoke graph generation."})

        run_id = await orchestrator.start_graph_pipeline(
            pipeline_id=site_id,
            niche=niche,
            ontology=ontology,
        )
        active_graph_runs[site_id] = run_id

        final_status = await orchestrator.wait_for_run(run_id, cancel_event=cancel_event)
        await _set_site_graph_status(site_id, _terminal_graph_status(final_status))
        await event_manager.publish(site_id, {"type": "log", "message": f"Graph workflow finished with status: {final_status}"})
    except Exception as e:
        await _set_site_graph_status(site_id, "failed")
        await event_manager.publish(site_id, {"type": "log", "message": f"Graph workflow failed: {str(e)}"})
        print(f"Graph workflow failed: {e}")
    finally:
        active_graph_runs.pop(site_id, None)
        active_graph_workflows.pop(site_id, None)

from pydantic import BaseModel
from typing import Optional

class ProcessPendingDocRequest(BaseModel):
    action: str # "skip", "extract_all", "extract_partial"
    char_limit: Optional[int] = None

class EventPayload(BaseModel):
    type: str
    message: str
    processed_chunks: int = 0
    total_chunks: int = 0
    current_phase: str = ""

@router.post("/internal/events/{site_id}")
async def receive_worker_event(site_id: str, payload: EventPayload):
    # The worker posts here, and FastAPI pushes it into the in-memory queue for the UI
    await event_manager.publish(site_id, payload.model_dump())
    return {"status": "ok"}

async def process_pending_document_worker(site_id: str, doc_id: str, url: str, action: str, char_limit: Optional[int], niche: str):
    from src.agents.nodes import scrape_node, bouncer_node, vector_storage_node
    from src.db.session import AsyncSessionLocal
    
    if action == "skip":
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(PendingDocument).where(PendingDocument.id == doc_id))
            doc = result.scalars().first()
            if doc:
                doc.status = "skipped"
                await session.commit()
        return
        
    await event_manager.publish(site_id, {"type": "log", "message": f"[TargetedWorker] Starting extraction for {url}"})
    
    state = {
        "pipeline_id": site_id,
        "niche": niche,
        "urls_to_scrape": [url],
        "current_url": None,
        "raw_text": None,
    }
    
    # 1. Scrape
    state = await scrape_node(state)
    
    if not state.get("raw_text"):
        await event_manager.publish(site_id, {"type": "log", "message": f"[TargetedWorker] Failed to extract text for {url}"})
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(PendingDocument).where(PendingDocument.id == doc_id))
            doc = result.scalars().first()
            if doc:
                doc.status = "failed"
                await session.commit()
        return
        
    # Apply char limit if partial
    if action == "extract_partial" and char_limit:
        state["raw_text"] = state["raw_text"][:char_limit]
        await event_manager.publish(site_id, {"type": "log", "message": f"[TargetedWorker] Truncated text to {char_limit} characters."})
        
    # 2. Bouncer (Bypass for manual extraction)
    state["is_relevant"] = True
    state["relevance_reason"] = "Manual extraction bypass"
    
    # 3. Vector Storage
    state = await vector_storage_node(state)
    
    # Mark as processed
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PendingDocument).where(PendingDocument.id == doc_id))
        doc = result.scalars().first()
        if doc:
            doc.status = "processed"
            await session.commit()
            
    await event_manager.publish(site_id, {"type": "log", "message": f"[TargetedWorker] Successfully processed large document {url}"})

@router.get("/pipelines/{site_id}/pending-documents")
async def get_pending_documents(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    result = await db.execute(
        select(PendingDocument)
        .where(PendingDocument.site_id == site_id, PendingDocument.status == "pending")
        .order_by(PendingDocument.created_at.desc())
    )
    docs = result.scalars().all()
    
    return [
        {
            "id": str(doc.id),
            "url": doc.url,
            "estimated_size": doc.estimated_size,
            "created_at": doc.created_at.isoformat() if doc.created_at else None
        }
        for doc in docs
    ]

@router.post("/pipelines/{site_id}/pending-documents/{doc_id}/process")
async def process_pending_document(
    site_id: str,
    doc_id: str,
    request: ProcessPendingDocRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    result = await db.execute(select(PendingDocument).where(PendingDocument.id == doc_id, PendingDocument.site_id == site_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Pending document not found")
        
    if doc.status not in ["pending", "failed", "rejected", "processing"]:
        raise HTTPException(status_code=400, detail=f"Document is no longer pending (status: {doc.status})")

    doc.status = "processing"
    await db.commit()

    background_tasks.add_task(
        process_pending_document_worker, 
        site_id, 
        doc_id, 
        doc.url, 
        request.action, 
        request.char_limit,
        site.name
    )
    
    return {"message": "Processing started"}

@router.get("/pipelines/{site_id}/logs")
async def stream_pipeline_logs(site_id: str, request: Request):
    async def event_generator():
        q = event_manager.subscribe(site_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            event_manager.unsubscribe(site_id, q)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/pipelines/{site_id}/acquire", status_code=202)
async def trigger_acquisition(
    site_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Trigger background task
    if site_id in active_workflows:
        return {"message": "Acquisition already running"}
        
    cancel_event = asyncio.Event()
    active_workflows[site_id] = cancel_event
    background_tasks.add_task(run_acquisition_workflow, str(site.id), site.name, site.ontology, cancel_event)
    
    return {"message": "Data acquisition started in background"}

@router.post("/pipelines/{site_id}/cancel", status_code=200)
async def cancel_acquisition(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if site_id in active_workflows:
        active_workflows[site_id].set()
        await orchestrator.cancel_pipeline(site_id)
        return {"message": "Cancellation requested"}
    
    return {"message": "No active workflow found"}

@router.post("/pipelines/{site_id}/generate-graph", status_code=202)
async def generate_graph(
    site_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if site_id in active_workflows:
        raise HTTPException(status_code=409, detail="Acquisition is still running for this pipeline")

    if site_id in active_graph_workflows:
        return {"message": "Graph generation already running or queued"}

    site.graph_status = "queued"
    await db.commit()
    cancel_event = asyncio.Event()
    active_graph_workflows[site_id] = cancel_event
    background_tasks.add_task(run_graph_workflow, str(site.id), site.name, site.ontology, cancel_event)
    
    return {"message": "Graph generation queued"}

@router.post("/pipelines/{site_id}/cancel-graph", status_code=200)
async def cancel_graph_generation(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if site_id in active_graph_workflows:
        active_graph_workflows[site_id].set()
        run_id = active_graph_runs.get(site_id)
        if run_id:
            await orchestrator.cancel_run(run_id)
        site.graph_status = "cancelled"
        await db.commit()
        return {"message": "Graph generation cancellation requested"}

    if site.graph_status in ["queued", "processing"]:
        site.graph_status = "cancelled"
        await db.commit()
        return {"message": "Graph generation marked cancelled"}
    
    return {"message": "No active graph generation workflow found"}

@router.get("/pipelines/{site_id}/entities")
async def get_pipeline_entities(
    site_id: str,
    theme: Optional[str] = "full",
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver
    
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    entities = []
    relationships = []

    def _node_payload(record: dict, prefix: str) -> dict:
        return {
            "id": str(record[f"{prefix}_id"]),
            "name": record[f"{prefix}_name"],
            "type": record[f"{prefix}_type"],
            "summary": record.get(f"{prefix}_summary"),
            "source_url": record.get(f"{prefix}_url"),
            "community_key": record.get(f"{prefix}_community_key"),
            "community_name": record.get(f"{prefix}_community_name"),
            "community_summary": record.get(f"{prefix}_community_summary"),
            "community_rank": record.get(f"{prefix}_community_rank"),
            "member_count": record.get(f"{prefix}_member_count"),
            "relationship_count": record.get(f"{prefix}_relationship_count"),
        }

    async with driver.session() as session:
        if theme == "documents":
            query = """
            MATCH (d:Document {pipeline_id: $pipeline_id})
            WITH collect(d) AS all_docs
            UNWIND all_docs AS d
            OPTIONAL MATCH (d)-[r:SIMILAR_TO|MENTIONS]-(t)
            WHERE t IS NULL OR t:Document OR
                  (t:CanonicalEntity AND 1 < COUNT { (t)<-[:MENTIONS]-(:Document {pipeline_id: $pipeline_id}) } <= 15)
            RETURN id(d) AS source_id,
                   coalesce(d.title, d.url) AS source_name,
                   'Document' AS source_type,
                   null AS source_summary,
                   null AS source_community_key,
                   null AS source_community_name,
                   null AS source_community_summary,
                   null AS source_community_rank,
                   null AS source_member_count,
                   null AS source_relationship_count,
                   d.url AS source_url,
                   id(t) AS target_id,
                   coalesce(t.title, t.name) AS target_name,
                   CASE WHEN t:Document THEN 'Document' ELSE t.type END AS target_type,
                   CASE WHEN t:CanonicalEntity THEN coalesce(t.community_summary, t.description) ELSE null END AS target_summary,
                   CASE WHEN t:CanonicalEntity THEN t.community_key ELSE null END AS target_community_key,
                   CASE WHEN t:CanonicalEntity THEN t.community_name ELSE null END AS target_community_name,
                   CASE WHEN t:CanonicalEntity THEN t.community_summary ELSE null END AS target_community_summary,
                   CASE WHEN t:CanonicalEntity THEN t.community_rank ELSE null END AS target_community_rank,
                   null AS target_member_count,
                   null AS target_relationship_count,
                   t.url AS target_url,
                   coalesce(r.type, type(r)) AS rel_type,
                   CASE WHEN type(r) = 'SIMILAR_TO' THEN r.weight ELSE 0.5 END AS weight,
                   [] AS quotes,
                   [] AS source_urls
            ORDER BY weight DESC
            LIMIT 2500
            """
        elif theme == "investors":
            query = """
            MATCH (investor:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH]-(neighbor:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE investor.type = 'Investor'
              AND (
                neighbor.type IN ['Company', 'Asset', 'ServiceProvider', 'Person', 'RegulatoryBody']
                OR r.type IN ['INVESTED_IN', 'ACQUIRED', 'OWNS_OR_CONTROLS', 'ADVISED', 'OPERATES_IN']
              )
            WITH investor AS s,
                 r,
                 neighbor AS t,
                 coalesce(r.weight, 1.0)
                   + CASE WHEN r.type IN ['INVESTED_IN', 'ACQUIRED', 'OWNS_OR_CONTROLS'] THEN 25 ELSE 0 END
                   + CASE WHEN t.type IN ['Company', 'Asset'] THEN 15 ELSE 0 END AS score
            RETURN id(s) AS source_id,
                   s.name AS source_name,
                   s.type AS source_type,
                   coalesce(s.community_summary, s.description) AS source_summary,
                   s.community_key AS source_community_key,
                   s.community_name AS source_community_name,
                   s.community_summary AS source_community_summary,
                   s.community_rank AS source_community_rank,
                   null AS source_member_count,
                   null AS source_relationship_count,
                   null AS source_url,
                   id(t) AS target_id,
                   t.name AS target_name,
                   t.type AS target_type,
                   coalesce(t.community_summary, t.description) AS target_summary,
                   t.community_key AS target_community_key,
                   t.community_name AS target_community_name,
                   t.community_summary AS target_community_summary,
                   t.community_rank AS target_community_rank,
                   null AS target_member_count,
                   null AS target_relationship_count,
                   null AS target_url,
                   coalesce(r.type, type(r)) AS rel_type,
                   coalesce(r.weight, score) AS weight,
                   r.quotes AS quotes,
                   r.source_urls AS source_urls
            ORDER BY score DESC
            LIMIT 2500
            """
        elif theme == "companies":
            query = """
            MATCH (s:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH]-(t:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE s.type IN ['Company', 'Investor', 'ServiceProvider', 'Asset']
               OR t.type IN ['Company', 'Investor', 'ServiceProvider', 'Asset']
            RETURN id(s) AS source_id,
                   s.name AS source_name,
                   s.type AS source_type,
                   coalesce(s.community_summary, s.description) AS source_summary,
                   s.community_key AS source_community_key,
                   s.community_name AS source_community_name,
                   s.community_summary AS source_community_summary,
                   s.community_rank AS source_community_rank,
                   null AS source_member_count,
                   null AS source_relationship_count,
                   null AS source_url,
                   id(t) AS target_id,
                   t.name AS target_name,
                   t.type AS target_type,
                   coalesce(t.community_summary, t.description) AS target_summary,
                   t.community_key AS target_community_key,
                   t.community_name AS target_community_name,
                   t.community_summary AS target_community_summary,
                   t.community_rank AS target_community_rank,
                   null AS target_member_count,
                   null AS target_relationship_count,
                   null AS target_url,
                   coalesce(r.type, type(r)) AS rel_type,
                   r.weight AS weight,
                   r.quotes AS quotes,
                   r.source_urls AS source_urls
            ORDER BY r.weight DESC
            LIMIT 2500
            """
        elif theme == "communities":
            query = """
            MATCH (community:Community {pipeline_id: $pipeline_id})
            OPTIONAL MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id})-[r:BELONGS_TO {pipeline_id: $pipeline_id}]->(community)
            RETURN id(entity) AS source_id,
                   entity.name AS source_name,
                   entity.type AS source_type,
                   coalesce(entity.community_summary, entity.description) AS source_summary,
                   entity.community_key AS source_community_key,
                   entity.community_name AS source_community_name,
                   entity.community_summary AS source_community_summary,
                   entity.community_rank AS source_community_rank,
                   null AS source_member_count,
                   null AS source_relationship_count,
                   null AS source_url,
                   id(community) AS target_id,
                   community.name AS target_name,
                   'Community' AS target_type,
                   community.summary AS target_summary,
                   community.community_key AS target_community_key,
                   community.name AS target_community_name,
                   community.summary AS target_community_summary,
                   null AS target_community_rank,
                   community.member_count AS target_member_count,
                   community.relationship_count AS target_relationship_count,
                   null AS target_url,
                   coalesce(r.type, type(r)) AS rel_type,
                   coalesce(r.membership_rank, 1.0) AS weight,
                   [] AS quotes,
                   [] AS source_urls
            ORDER BY community.member_count DESC, r.membership_rank ASC
            LIMIT 4000
            """
        elif theme == "regulatory":
            query = """
            MATCH (s:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH]-(t:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE (s.type IN ['RegulatoryBody'] AND t.type IN ['Company', 'Investor', 'ServiceProvider', 'Asset'])
               OR (t.type IN ['RegulatoryBody'] AND s.type IN ['Company', 'Investor', 'ServiceProvider', 'Asset'])
            RETURN id(s) AS source_id,
                   s.name AS source_name,
                   s.type AS source_type,
                   coalesce(s.community_summary, s.description) AS source_summary,
                   s.community_key AS source_community_key,
                   s.community_name AS source_community_name,
                   s.community_summary AS source_community_summary,
                   s.community_rank AS source_community_rank,
                   null AS source_member_count,
                   null AS source_relationship_count,
                   null AS source_url,
                   id(t) AS target_id,
                   t.name AS target_name,
                   t.type AS target_type,
                   coalesce(t.community_summary, t.description) AS target_summary,
                   t.community_key AS target_community_key,
                   t.community_name AS target_community_name,
                   t.community_summary AS target_community_summary,
                   t.community_rank AS target_community_rank,
                   null AS target_member_count,
                   null AS target_relationship_count,
                   null AS target_url,
                   coalesce(r.type, type(r)) AS rel_type,
                   r.weight AS weight,
                   r.quotes AS quotes,
                   r.source_urls AS source_urls
            ORDER BY r.weight DESC
            LIMIT 2500
            """
        else:
            query = """
            MATCH (s:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH]->(t:CanonicalEntity {pipeline_id: $pipeline_id})
            WITH s,
                 r,
                 t,
                 coalesce(r.weight, 1.0)
                   + CASE WHEN s.type = 'Investor' OR t.type = 'Investor' THEN 100 ELSE 0 END
                   + CASE WHEN s.type IN ['Company', 'ServiceProvider', 'Asset'] OR t.type IN ['Company', 'ServiceProvider', 'Asset'] THEN 25 ELSE 0 END
                   + CASE WHEN r.type IN ['INVESTED_IN', 'ACQUIRED', 'OWNS_OR_CONTROLS', 'ADVISED', 'OPERATES_IN'] THEN 50 ELSE 0 END AS score
            WHERE score >= 25
            RETURN id(s) AS source_id,
                   s.name AS source_name,
                   s.type AS source_type,
                   coalesce(s.community_summary, s.description) AS source_summary,
                   s.community_key AS source_community_key,
                   s.community_name AS source_community_name,
                   s.community_summary AS source_community_summary,
                   s.community_rank AS source_community_rank,
                   null AS source_member_count,
                   null AS source_relationship_count,
                   null AS source_url,
                   id(t) AS target_id,
                   t.name AS target_name,
                   t.type AS target_type,
                   coalesce(t.community_summary, t.description) AS target_summary,
                   t.community_key AS target_community_key,
                   t.community_name AS target_community_name,
                   t.community_summary AS target_community_summary,
                   t.community_rank AS target_community_rank,
                   null AS target_member_count,
                   null AS target_relationship_count,
                   null AS target_url,
                   coalesce(r.type, type(r)) AS rel_type,
                   r.weight AS weight,
                   r.quotes AS quotes,
                   r.source_urls AS source_urls
            ORDER BY score DESC
            LIMIT 2500
            """

        result = await session.run(query, pipeline_id=site_id)
        records = await result.data()

        unique_nodes = {}
        for record in records:
            if record["source_id"] is not None and record["source_id"] not in unique_nodes:
                unique_nodes[record["source_id"]] = _node_payload(record, "source")

            if record["target_id"] is not None and record["target_id"] not in unique_nodes:
                unique_nodes[record["target_id"]] = _node_payload(record, "target")

            if record["rel_type"] is not None:
                relationships.append(
                    {
                        "source": str(record["source_id"]),
                        "source_name": record["source_name"],
                        "type": record["rel_type"],
                        "target": str(record["target_id"]),
                        "target_name": record["target_name"],
                        "weight": record["weight"],
                        "quotes": record["quotes"] or [],
                        "source_urls": record.get("source_urls") or [],
                    }
                )

        entities = list(unique_nodes.values())

    return {"entities": entities, "relationships": relationships}


@router.get("/pipelines/{site_id}/communities")
async def list_pipeline_communities(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver

    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (community:Community {pipeline_id: $pipeline_id})
            OPTIONAL MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id})-[membership:BELONGS_TO {pipeline_id: $pipeline_id}]->(community)
            WITH community, entity, membership
            ORDER BY coalesce(membership.membership_rank, 999999), entity.name
            WITH community, collect(
                CASE
                    WHEN entity IS NULL THEN null
                    ELSE {
                        node_id: id(entity),
                        name: entity.name,
                        type: entity.type,
                        community_rank: membership.membership_rank
                    }
                END
            ) AS raw_members
            RETURN community.community_key AS community_key,
                   coalesce(community.name, 'Untitled Community') AS name,
                   community.summary AS summary,
                   coalesce(community.member_count, size([member IN raw_members WHERE member IS NOT NULL | member])) AS member_count,
                   coalesce(community.relationship_count, 0) AS relationship_count,
                   community.algorithm AS algorithm,
                   community.algorithm_version AS algorithm_version,
                   [member IN raw_members WHERE member IS NOT NULL | member][0..8] AS top_members
            ORDER BY member_count DESC, name ASC
            """,
            pipeline_id=site_id,
        )
        communities = await result.data()

    return communities


@router.get("/pipelines/{site_id}/communities/export")
async def export_pipeline_communities(
    site_id: str,
    community_key: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver

    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    communities_csv = io.StringIO()
    memberships_csv = io.StringIO()
    internal_relationships_csv = io.StringIO()
    bridges_csv = io.StringIO()

    communities_writer = csv.writer(communities_csv)
    communities_writer.writerow(
        ["CommunityKey", "CommunityName", "Summary", "MemberCount", "RelationshipCount", "Algorithm", "AlgorithmVersion"]
    )

    memberships_writer = csv.writer(memberships_csv)
    memberships_writer.writerow(
        ["CommunityKey", "CommunityName", "EntityNodeId", "EntityName", "EntityType", "CommunityRank"]
    )

    internal_relationships_writer = csv.writer(internal_relationships_csv)
    internal_relationships_writer.writerow(
        ["CommunityKey", "CommunityName", "SourceNodeId", "SourceName", "RelationshipType", "TargetNodeId", "TargetName", "Weight"]
    )

    bridges_writer = csv.writer(bridges_csv)
    bridges_writer.writerow(
        ["SourceCommunityKey", "SourceCommunityName", "TargetCommunityKey", "TargetCommunityName", "InteractionCount"]
    )

    async with driver.session() as session:
        communities_res = await session.run(
            """
            MATCH (community:Community {pipeline_id: $pipeline_id})
            WHERE $community_key IS NULL OR community.community_key = $community_key
            RETURN community.community_key AS community_key,
                   coalesce(community.name, 'Untitled Community') AS community_name,
                   community.summary AS summary,
                   coalesce(community.member_count, 0) AS member_count,
                   coalesce(community.relationship_count, 0) AS relationship_count,
                   community.algorithm AS algorithm,
                   community.algorithm_version AS algorithm_version
            ORDER BY member_count DESC, community_name ASC
            """,
            pipeline_id=site_id,
            community_key=community_key,
        )
        communities_records = await communities_res.data()

        memberships_res = await session.run(
            """
            MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id})-[membership:BELONGS_TO {pipeline_id: $pipeline_id}]->(community:Community {pipeline_id: $pipeline_id})
            WHERE $community_key IS NULL OR community.community_key = $community_key
            RETURN community.community_key AS community_key,
                   coalesce(community.name, 'Untitled Community') AS community_name,
                   id(entity) AS entity_node_id,
                   entity.name AS entity_name,
                   entity.type AS entity_type,
                   membership.membership_rank AS community_rank
            ORDER BY community_name ASC, coalesce(community_rank, 999999), entity_name ASC
            """,
            pipeline_id=site_id,
            community_key=community_key,
        )
        memberships_records = await memberships_res.data()

        internal_relationships_res = await session.run(
            """
            MATCH (source:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH {pipeline_id: $pipeline_id}]->(target:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE source.community_key IS NOT NULL
              AND source.community_key = target.community_key
              AND ($community_key IS NULL OR source.community_key = $community_key)
            RETURN source.community_key AS community_key,
                   coalesce(source.community_name, source.community_key) AS community_name,
                   id(source) AS source_node_id,
                   source.name AS source_name,
                   coalesce(r.type, 'INTERACTS_WITH') AS relationship_type,
                   id(target) AS target_node_id,
                   target.name AS target_name,
                   coalesce(r.weight, 1.0) AS weight
            ORDER BY community_name ASC, weight DESC, source_name ASC, target_name ASC
            """,
            pipeline_id=site_id,
            community_key=community_key,
        )
        internal_relationship_records = await internal_relationships_res.data()

        bridge_res = await session.run(
            """
            MATCH (source:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH {pipeline_id: $pipeline_id}]-(target:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE source.community_key IS NOT NULL
              AND target.community_key IS NOT NULL
              AND source.community_key <> target.community_key
              AND ($community_key IS NULL OR source.community_key = $community_key OR target.community_key = $community_key)
            WITH CASE
                     WHEN source.community_key < target.community_key THEN source.community_key
                     ELSE target.community_key
                 END AS source_community_key,
                 CASE
                     WHEN source.community_key < target.community_key THEN coalesce(source.community_name, source.community_key)
                     ELSE coalesce(target.community_name, target.community_key)
                 END AS source_community_name,
                 CASE
                     WHEN source.community_key < target.community_key THEN target.community_key
                     ELSE source.community_key
                 END AS target_community_key,
                 CASE
                     WHEN source.community_key < target.community_key THEN coalesce(target.community_name, target.community_key)
                     ELSE coalesce(source.community_name, source.community_key)
                 END AS target_community_name,
                 count(r) AS interaction_count
            RETURN source_community_key, source_community_name, target_community_key, target_community_name, interaction_count
            ORDER BY interaction_count DESC, source_community_name ASC, target_community_name ASC
            """,
            pipeline_id=site_id,
            community_key=community_key,
        )
        bridge_records = await bridge_res.data()

    if community_key and not communities_records:
        raise HTTPException(status_code=404, detail="Community not found")

    for record in communities_records:
        communities_writer.writerow(
            [
                record["community_key"],
                record["community_name"],
                record["summary"] or "",
                record["member_count"],
                record["relationship_count"],
                record.get("algorithm") or "",
                record.get("algorithm_version") or "",
            ]
        )

    for record in memberships_records:
        memberships_writer.writerow(
            [
                record["community_key"],
                record["community_name"],
                record["entity_node_id"],
                record["entity_name"],
                record["entity_type"],
                record.get("community_rank") or "",
            ]
        )

    for record in internal_relationship_records:
        internal_relationships_writer.writerow(
            [
                record["community_key"],
                record["community_name"],
                record["source_node_id"],
                record["source_name"],
                record["relationship_type"],
                record["target_node_id"],
                record["target_name"],
                record["weight"],
            ]
        )

    for record in bridge_records:
        bridges_writer.writerow(
            [
                record["source_community_key"],
                record["source_community_name"],
                record["target_community_key"],
                record["target_community_name"],
                record["interaction_count"],
            ]
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("communities.csv", communities_csv.getvalue())
        zip_file.writestr("community_memberships.csv", memberships_csv.getvalue())
        zip_file.writestr("community_internal_relationships.csv", internal_relationships_csv.getvalue())
        zip_file.writestr("community_bridges.csv", bridges_csv.getvalue())

    zip_buffer.seek(0)
    filename = f"community_export_{site_id}.zip" if community_key else f"communities_export_{site_id}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pipelines/{site_id}/communities/{community_key}")
async def get_pipeline_community(
    site_id: str,
    community_key: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver

    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    async with driver.session() as session:
        community_res = await session.run(
            """
            MATCH (community:Community {pipeline_id: $pipeline_id, community_key: $community_key})
            OPTIONAL MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id})-[membership:BELONGS_TO {pipeline_id: $pipeline_id, community_key: $community_key}]->(community)
            WITH community, entity, membership
            ORDER BY coalesce(membership.membership_rank, 999999), entity.name
            WITH community, collect(
                CASE
                    WHEN entity IS NULL THEN null
                    ELSE {
                        node_id: id(entity),
                        canonical_key: entity.canonical_key,
                        name: entity.name,
                        type: entity.type,
                        community_rank: membership.membership_rank,
                        summary: coalesce(entity.community_summary, entity.description)
                    }
                END
            ) AS raw_members
            RETURN community.community_key AS community_key,
                   coalesce(community.name, 'Untitled Community') AS name,
                   community.summary AS summary,
                   coalesce(community.member_count, size([member IN raw_members WHERE member IS NOT NULL | member])) AS member_count,
                   coalesce(community.relationship_count, 0) AS relationship_count,
                   community.algorithm AS algorithm,
                   community.algorithm_version AS algorithm_version,
                   [member IN raw_members WHERE member IS NOT NULL | member] AS members
            """,
            pipeline_id=site_id,
            community_key=community_key,
        )
        community_record = await community_res.single()
        if not community_record:
            raise HTTPException(status_code=404, detail="Community not found")

        internal_relationships_res = await session.run(
            """
            MATCH (source:CanonicalEntity {pipeline_id: $pipeline_id, community_key: $community_key})-[r:INTERACTS_WITH {pipeline_id: $pipeline_id}]->(target:CanonicalEntity {pipeline_id: $pipeline_id, community_key: $community_key})
            RETURN id(source) AS source_id,
                   source.name AS source_name,
                   id(target) AS target_id,
                   target.name AS target_name,
                   coalesce(r.type, 'INTERACTS_WITH') AS relationship_type,
                   coalesce(r.weight, 1.0) AS weight
            ORDER BY weight DESC, source_name ASC, target_name ASC
            LIMIT 50
            """,
            pipeline_id=site_id,
            community_key=community_key,
        )
        internal_relationships = await internal_relationships_res.data()

        related_communities_res = await session.run(
            """
            MATCH (source:CanonicalEntity {pipeline_id: $pipeline_id, community_key: $community_key})-[r:INTERACTS_WITH {pipeline_id: $pipeline_id}]-(target:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE target.community_key IS NOT NULL AND target.community_key <> $community_key
            WITH target.community_key AS community_key,
                 coalesce(target.community_name, target.community_key) AS community_name,
                 count(r) AS interaction_count,
                 collect(DISTINCT target.name)[0..6] AS example_members
            RETURN community_key, community_name, interaction_count, example_members
            ORDER BY interaction_count DESC, community_name ASC
            LIMIT 20
            """,
            pipeline_id=site_id,
            community_key=community_key,
        )
        related_communities = await related_communities_res.data()

    return {
        "community_key": community_record["community_key"],
        "name": community_record["name"],
        "summary": community_record["summary"],
        "member_count": community_record["member_count"],
        "relationship_count": community_record["relationship_count"],
        "algorithm": community_record.get("algorithm"),
        "algorithm_version": community_record.get("algorithm_version"),
        "members": community_record["members"],
        "internal_relationships": internal_relationships,
        "related_communities": related_communities,
    }

@router.get("/pipelines/{site_id}/nodes/{node_id}/explore")
async def explore_node_group(
    site_id: str,
    node_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver
    from src.services.rag_service import generate_rag_insight
    import os
    
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    entities = {}
    relationships = []
    central_node = None
    
    async with driver.session() as session:
        # Fetch the central node and its immediate neighbors
        result = await session.run(
            """
            MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE id(c) = $node_id
            
            OPTIONAL MATCH (c)-[r1:INTERACTS_WITH]-(n1:CanonicalEntity {pipeline_id: $pipeline_id})
            
            RETURN 
                id(c) as central_id, c.name as central_name, c.type as central_type, c.description as central_description,
                properties(c) as central_props,
                id(n1) as neighbor_id, n1.name as neighbor_name, n1.type as neighbor_type, n1.description as neighbor_description,
                r1.type as rel_type, r1.weight as weight, r1.quotes as quotes, r1.source_urls as source_urls,
                CASE WHEN r1 IS NOT NULL THEN startNode(r1) = c ELSE null END as is_outgoing
            """, 
            pipeline_id=site_id,
            node_id=int(node_id)
        )
        records = await result.data()
        
        if not records or records[0]["central_id"] is None:
            raise HTTPException(status_code=404, detail="Node not found")
            
        central_record = records[0]
        central_node = {
            "id": str(central_record["central_id"]),
            "name": central_record["central_name"],
            "type": central_record["central_type"],
            "description": central_record.get("central_description"),
            "props": central_record.get("central_props", {}),
            "investor_insight": None
        }
        entities[str(central_record["central_id"])] = central_node
        
        for record in records:
            if record["neighbor_id"] is not None:
                n_id = str(record["neighbor_id"])
                if n_id not in entities:
                    entities[n_id] = {
                        "id": n_id,
                        "name": record["neighbor_name"],
                        "type": record["neighbor_type"],
                        "description": record.get("neighbor_description")
                    }
                
                # Determine source and target based on direction
                source_id = str(central_record["central_id"]) if record["is_outgoing"] else n_id
                target_id = n_id if record["is_outgoing"] else str(central_record["central_id"])
                source_name = central_record["central_name"] if record["is_outgoing"] else record["neighbor_name"]
                target_name = record["neighbor_name"] if record["is_outgoing"] else central_record["central_name"]
                
                # Avoid duplicates if multiple paths exist (though INTERACTS_WITH is usually merged)
                rel_exists = any(r["source"] == source_id and r["target"] == target_id and r["type"] == record["rel_type"] for r in relationships)
                if not rel_exists:
                    relationships.append({
                        "source": source_id,
                        "source_name": source_name,
                        "type": record["rel_type"],
                        "target": target_id,
                        "target_name": target_name,
                        "weight": record["weight"],
                        "quotes": record["quotes"] or [],
                        "source_urls": record.get("source_urls") or []
                    })
                    
        # Always generate a new investor insight using the RAG service
        try:
            insight = await generate_rag_insight(site_id, int(node_id), "Entity")
            central_node["investor_insight"] = insight
        except Exception as e:
            print(f"Failed to generate investor insight: {e}")
            central_node["investor_insight"] = "Analysis could not be generated at this time."

    return {
        "central_node": central_node,
        "entities": list(entities.values()),
        "relationships": relationships
    }

@router.get("/pipelines/{site_id}/documents/{node_id}/explore")
async def explore_document_group(
    site_id: str,
    node_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver
    from src.services.rag_service import generate_rag_insight
    
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    entities = {}
    relationships = []
    central_node = None
    
    async with driver.session() as session:
        # Fetch the central document and its connections (SIMILAR_TO docs and MENTIONS entities)
        result = await session.run(
            """
            MATCH (d:Document {pipeline_id: $pipeline_id})
            WHERE id(d) = $node_id
            
            OPTIONAL MATCH (d)-[r_sim:SIMILAR_TO]-(sim_doc:Document {pipeline_id: $pipeline_id})
            OPTIONAL MATCH (d)-[r_mentions:MENTIONS]->(ent:CanonicalEntity {pipeline_id: $pipeline_id})
            
            RETURN 
                id(d) as central_id, coalesce(d.title, d.url) as central_name, 'Document' as central_type, d.url as central_url,
                id(sim_doc) as sim_id, coalesce(sim_doc.title, sim_doc.url) as sim_name, 'Document' as sim_type, sim_doc.url as sim_url, r_sim.weight as sim_weight,
                id(ent) as ent_id, ent.name as ent_name, ent.type as ent_type
            """, 
            pipeline_id=site_id,
            node_id=int(node_id)
        )
        records = await result.data()
        
        if not records or records[0]["central_id"] is None:
            raise HTTPException(status_code=404, detail="Document not found")
            
        central_record = records[0]
        central_node = {
            "id": str(central_record["central_id"]),
            "name": central_record["central_name"],
            "type": central_record["central_type"],
            "source_url": central_record["central_url"],
            "investor_insight": None
        }
        entities[str(central_record["central_id"])] = central_node
        
        for record in records:
            # Handle SIMILAR_TO documents
            if record["sim_id"] is not None:
                n_id = str(record["sim_id"])
                if n_id not in entities:
                    entities[n_id] = {
                        "id": n_id,
                        "name": record["sim_name"],
                        "type": record["sim_type"],
                        "source_url": record["sim_url"]
                    }
                
                rel_exists = any(r["source"] == str(central_record["central_id"]) and r["target"] == n_id and r["type"] == 'SIMILAR_TO' for r in relationships)
                if not rel_exists:
                    relationships.append({
                        "source": str(central_record["central_id"]),
                        "source_name": central_record["central_name"],
                        "type": "SIMILAR_TO",
                        "target": n_id,
                        "target_name": record["sim_name"],
                        "weight": record["sim_weight"],
                        "quotes": [],
                        "source_urls": []
                    })
                    
            # Handle MENTIONS entities
            if record["ent_id"] is not None:
                n_id = str(record["ent_id"])
                if n_id not in entities:
                    entities[n_id] = {
                        "id": n_id,
                        "name": record["ent_name"],
                        "type": record["ent_type"]
                    }
                
                rel_exists = any(r["source"] == str(central_record["central_id"]) and r["target"] == n_id and r["type"] == 'MENTIONS' for r in relationships)
                if not rel_exists:
                    relationships.append({
                        "source": str(central_record["central_id"]),
                        "source_name": central_record["central_name"],
                        "type": "MENTIONS",
                        "target": n_id,
                        "target_name": record["ent_name"],
                        "weight": 0.5,
                        "quotes": [],
                        "source_urls": []
                    })
                    
        # Generate RAG insight for the document
        try:
            insight = await generate_rag_insight(site_id, int(node_id), "Document")
            central_node["investor_insight"] = insight
        except Exception as e:
            print(f"Failed to generate document insight: {e}")
            central_node["investor_insight"] = "Analysis could not be generated at this time."

    return {
        "central_node": central_node,
        "entities": list(entities.values()),
        "relationships": relationships
    }

@router.get("/pipelines/{site_id}/export")
async def export_pipeline_graph(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver
    
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    nodes_csv = io.StringIO()
    edges_csv = io.StringIO()
    
    nodes_writer = csv.writer(nodes_csv)
    nodes_writer.writerow(["Id", "Label", "EntityType"])
    
    edges_writer = csv.writer(edges_csv)
    edges_writer.writerow(["Source", "Target", "Type", "Label", "Weight"])
    
    async with driver.session() as session:
        # Fetch Nodes
        nodes_res = await session.run(
            "MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id}) RETURN id(c) AS Id, c.name AS Label, c.type AS EntityType",
            pipeline_id=site_id
        )
        nodes_records = await nodes_res.data()
        for record in nodes_records:
            nodes_writer.writerow([record["Id"], record["Label"], record["EntityType"]])
            
        # Fetch Edges
        edges_res = await session.run(
            """
            MATCH (cs:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH {pipeline_id: $pipeline_id}]->(ct:CanonicalEntity {pipeline_id: $pipeline_id})
            WITH id(cs) AS Source, id(ct) AS Target, coalesce(r.type, 'INTERACTS_WITH') AS Label, coalesce(r.weight, 1.0) AS Weight
            RETURN Source, Target, 'Directed' AS Type, Label, Weight
            """,
            pipeline_id=site_id
        )
        edges_records = await edges_res.data()
        for record in edges_records:
            edges_writer.writerow([record["Source"], record["Target"], record["Type"], record["Label"], record["Weight"]])

    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("nodes.csv", nodes_csv.getvalue())
        zip_file.writestr("edges.csv", edges_csv.getvalue())
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="graph_export_{site_id}.zip"'}
    )

@router.get("/pipelines/{site_id}/documents")
async def get_pipeline_documents(
    site_id: str,
    source_url: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.models.relational import Document as PGDocument
    from sqlalchemy import func, Integer
    
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Get data sources for this site
    result = await db.execute(select(DataSource.id).where(DataSource.site_id == site_id))
    data_source_ids = result.scalars().all()
    
    if not data_source_ids:
        return {"total_chunks": 0, "chunks": []}
        
    query = select(PGDocument).where(PGDocument.data_source_id.in_(data_source_ids))
    count_query = select(func.count()).select_from(PGDocument).where(PGDocument.data_source_id.in_(data_source_ids))
    
    if source_url:
        query = query.where(PGDocument.metadata_json["source_url"].astext == source_url)
        count_query = count_query.where(PGDocument.metadata_json["source_url"].astext == source_url)
        
    # Get total count
    result = await db.execute(count_query)
    total_chunks = result.scalar() or 0
    
    # Get most recent chunks (limit 50 if no source_url, otherwise get all or more)
    if not source_url:
        query = query.order_by(PGDocument.processed_at.desc()).limit(50)
    else:
        query = query.order_by(PGDocument.metadata_json["chunk_index"].astext.cast(Integer))
        
    result = await db.execute(query)
    documents = result.scalars().all()
    
    chunks = []
    for doc in documents:
        chunks.append({
            "id": str(doc.id),
            "title": doc.title,
            "text_snippet": doc.raw_text[:200] + "..." if doc.raw_text and len(doc.raw_text) > 200 else doc.raw_text,
            "source_url": doc.metadata_json.get("source_url") if doc.metadata_json else None,
            "created_at": doc.processed_at.isoformat() if doc.processed_at else None
        })
        
    return {"total_chunks": total_chunks, "chunks": chunks}

@router.get("/pipelines/{site_id}/sources")
async def get_pipeline_sources(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.models.relational import Document as PGDocument
    from src.services.storage import storage
    
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Get data sources for this site
    result = await db.execute(select(DataSource.id).where(DataSource.site_id == site_id))
    data_source_ids = result.scalars().all()
    
    if not data_source_ids:
        return []
        
    # Get distinct source URLs and their storage objects
    # We'll use a distinct on the source_url from metadata_json
    result = await db.execute(
        select(PGDocument.metadata_json)
        .where(PGDocument.data_source_id.in_(data_source_ids))
    )
    
    metadata_list = result.scalars().all()
    
    unique_sources = {}
    for meta in metadata_list:
        if not meta:
            continue
            
        source_url = meta.get("source_url")
        if not source_url or source_url in unique_sources:
            continue
            
        storage_object = meta.get("storage_object")
        
        # Determine type from extension or default to HTML
        source_type = "html"
        if source_url.lower().endswith(".pdf"):
            source_type = "pdf"
        elif source_url.lower().endswith(".docx"):
            source_type = "docx"
        elif source_url.lower().endswith(".pptx"):
            source_type = "pptx"
        elif source_url.lower().endswith(".xlsx") or source_url.lower().endswith(".csv"):
            source_type = "spreadsheet"
            
        viewer_url = None
        if storage_object:
            viewer_url = storage.get_presigned_url(storage_object)
            
        unique_sources[source_url] = {
            "url": source_url,
            "type": source_type,
            "viewer_url": viewer_url
        }
        
    return list(unique_sources.values())

@router.get("/pipelines/{site_id}/documents/view")
async def view_document(
    site_id: str,
    source_url: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.models.relational import Document as PGDocument
    from src.services.storage import storage
    from sqlalchemy import Integer
    
    # Verify site exists and belongs to user's tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Get data sources for this site
    result = await db.execute(select(DataSource.id).where(DataSource.site_id == site_id))
    data_source_ids = result.scalars().all()
    
    if not data_source_ids:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Get the document
    query = select(PGDocument).where(
        PGDocument.data_source_id.in_(data_source_ids),
        PGDocument.metadata_json["source_url"].astext == source_url
    ).order_by(PGDocument.metadata_json["chunk_index"].astext.cast(Integer))
    
    result = await db.execute(query)
    documents = result.scalars().all()
    
    if not documents:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Determine type from extension or default to HTML
    source_type = "html"
    if source_url.lower().endswith(".pdf"):
        source_type = "pdf"
    elif source_url.lower().endswith(".docx"):
        source_type = "docx"
    elif source_url.lower().endswith(".pptx"):
        source_type = "pptx"
    elif source_url.lower().endswith(".xlsx") or source_url.lower().endswith(".csv"):
        source_type = "spreadsheet"
        
    # Check if we have a storage object for presigned URL
    storage_object = None
    for doc in documents:
        if doc.metadata_json and doc.metadata_json.get("storage_object"):
            storage_object = doc.metadata_json.get("storage_object")
            break
            
    viewer_url = None
    if storage_object:
        viewer_url = storage.get_presigned_url(storage_object)
        
    # Always return viewer_url if we have it
    if viewer_url:
        return {
            "type": source_type,
            "viewer_url": viewer_url,
            "title": documents[0].title or source_url,
            "source_url": source_url
        }
        
    # Otherwise, return the combined raw text
    combined_text = "\n\n".join([doc.raw_text for doc in documents if doc.raw_text])
    return {
        "type": "text",
        "content": combined_text,
        "title": documents[0].title or source_url,
        "source_url": source_url
    }

@router.post("/pipelines", status_code=201)
async def create_pipeline(
    config: PipelineConfig, 
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from sqlalchemy import func
    
    # 1. Get or create the Tenant for the authenticated user
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    
    if not tenant:
        tenant = Tenant(name=f"Tenant for {user_id}", auth_id=user_id)
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

    # 2. Check for existing Site for this niche
    if not config.niche:
        raise HTTPException(status_code=400, detail="Niche is required to create a pipeline.")

    result = await db.execute(
        select(Site).where(
            Site.tenant_id == tenant.id,
            func.lower(Site.name) == config.niche.lower()
        )
    )
    existing_site = result.scalars().first()

    if existing_site:
        return {"message": "Pipeline already exists", "site_id": str(existing_site.id)}

    # Convert schema to dict for JSONB
    ontology_data = config.schema_config.model_dump() if config.schema_config else {"entities": [], "relationships": []}

    site = Site(
        tenant_id=tenant.id,
        name=config.niche,
        description=f"Market map for {config.niche}",
        ontology=ontology_data
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)

    # 3. Create Data Sources
    for source in config.sources:
        db_source = DataSource(
            site_id=site.id,
            source_type=source.type,
            name=source.name,
            config={"url": source.url}
        )
        db.add(db_source)
    
    await db.commit()
    
    return {"message": "Pipeline deployed successfully", "site_id": str(site.id)}

@router.get("/pipelines")
async def list_pipelines(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.models.relational import Document as PGDocument
    from sqlalchemy import func
    
    # 1. Verify tenant
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        return []
        
    # 2. Get all sites for tenant
    result = await db.execute(
        select(Site).where(Site.tenant_id == tenant.id).order_by(Site.created_at.desc())
    )
    sites = result.scalars().all()
    
    # 3. Calculate document count for each site
    response_data = []
    for site in sites:
        # Get data sources for this site
        ds_result = await db.execute(select(DataSource.id).where(DataSource.site_id == site.id))
        data_source_ids = ds_result.scalars().all()
        
        doc_count = 0
        if data_source_ids:
            count_result = await db.execute(
                select(func.count()).select_from(PGDocument).where(PGDocument.data_source_id.in_(data_source_ids))
            )
            doc_count = count_result.scalar() or 0
            
        response_data.append({
            "id": str(site.id),
            "name": site.name,
            "created_at": site.created_at.isoformat() if site.created_at else None,
            "document_count": doc_count
        })
        
    return response_data


async def _require_owned_site(db: AsyncSession, site_id: str, user_id: str) -> Site:
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id))
    site = result.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return site


@router.get("/pipelines/{site_id}/enrichment-artifacts")
async def get_enrichment_artifacts(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant),
):
    from src.orchestrator.core.ledger_models import PipelineRun, TaskArtifact

    site = await _require_owned_site(db, site_id, user_id)
    result = await db.execute(
        select(TaskArtifact, PipelineRun)
        .join(PipelineRun, TaskArtifact.run_id == PipelineRun.id)
        .where(
            TaskArtifact.site_id == site.id,
            TaskArtifact.artifact_type == "company_enrichment_profile",
        )
        .order_by(TaskArtifact.created_at.desc())
    )

    items = []
    seen_companies: set[str] = set()
    for artifact, run in result.all():
        metadata_json = artifact.metadata_json or {}
        company_name = metadata_json.get("company_name") or artifact.artifact_key
        if company_name in seen_companies:
            continue
        seen_companies.add(company_name)
        items.append(
            {
                "company_name": company_name,
                "stage_estimate": metadata_json.get("stage_estimate"),
                "venture_scale_score": metadata_json.get("venture_scale_score"),
                "primary_sector": metadata_json.get("primary_sector"),
                "founder_count": metadata_json.get("founder_count", 0),
                "document_count": metadata_json.get("document_count", 0),
                "source_urls": metadata_json.get("source_urls", []),
                "source_document_ids": metadata_json.get("source_document_ids", []),
                "company_profile": metadata_json.get("company_profile", {}),
                "run_id": str(run.id),
                "run_status": run.status,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
        )

    return {"items": items}


@router.get("/pipelines/{site_id}/enrichments")
async def get_normalized_enrichments(
    site_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant),
):
    from src.orchestrator.core.enrichment_models import CompanyEnrichmentProfile
    from src.orchestrator.workers.enrichment_persistence import enrichment_tables_ready

    site = await _require_owned_site(db, site_id, user_id)
    if not await enrichment_tables_ready():
        return {"normalized_available": False, "items": []}

    result = await db.execute(
        select(CompanyEnrichmentProfile)
        .options(selectinload(CompanyEnrichmentProfile.founders))
        .where(CompanyEnrichmentProfile.site_id == site.id)
        .order_by(CompanyEnrichmentProfile.updated_at.desc())
    )
    profiles = result.scalars().all()

    items = []
    for profile in profiles:
        items.append(
            {
                "id": str(profile.id),
                "company_name": profile.company_name,
                "normalized_company_name": profile.normalized_company_name,
                "legal_name": profile.legal_name,
                "primary_url": profile.primary_url,
                "primary_sector": profile.primary_sector,
                "stage_estimate": profile.stage_estimate,
                "venture_scale_score": profile.venture_scale_score,
                "pitch_summary": profile.pitch_summary,
                "full_description": profile.full_description,
                "taxonomy": {
                    "l1": profile.taxonomy_l1,
                    "l2": profile.taxonomy_l2,
                    "l3": profile.taxonomy_l3,
                },
                "tech_stack": list(profile.tech_stack_json or []),
                "dimension_scores": dict(profile.dimension_scores_json or {}),
                "vc_dossier": dict(profile.vc_dossier_json or {}),
                "strategic_analysis": dict(profile.strategic_analysis_json or {}),
                "metric_rationales": dict(profile.metric_rationales_json or {}),
                "source_document_ids": list(profile.source_document_ids_json or []),
                "source_urls": list(profile.source_urls_json or []),
                "founders": [
                    {
                        "id": str(founder.id),
                        "name": founder.name,
                        "role": founder.role,
                        "bio": founder.bio,
                        "hometown": founder.hometown,
                        "linkedin_url": founder.linkedin_url,
                        "twitter_url": founder.twitter_url,
                        "previous_companies": list(founder.previous_companies_json or []),
                        "education": list(founder.education_json or []),
                        "is_technical": founder.is_technical,
                        "tags": list(founder.tags_json or []),
                    }
                    for founder in profile.founders
                ],
                "run_id": str(profile.run_id),
                "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            }
        )

    return {"normalized_available": True, "items": items}
