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

from src.db.session import get_db_session
from src.models.relational import Tenant, Site, DataSource, PendingDocument
from src.api.schemas import PipelineConfig
from src.api.auth import get_current_tenant
from src.agents.workflow import build_acquisition_graph
from src.api.events import event_manager

router = APIRouter()

# Global registry to track active workflows and their cancellation events
active_workflows: dict[str, asyncio.Event] = {}

async def run_acquisition_workflow(site_id: str, niche: str, ontology: dict, cancel_event: asyncio.Event):
    # Initialize the graph
    graph = build_acquisition_graph()
    
    # Initial state
    state = {
        "pipeline_id": site_id,
        "niche": niche,
        "schema_entities": ontology.get("entities", []),
        "schema_relationships": ontology.get("relationships", []),
        "search_queries": [],
        "urls_to_scrape": [],
        "current_url": None,
        "raw_text": None,
        "is_relevant": False,
        "relevance_reason": None,
        "extracted_entities": [],
        "extracted_relationships": [],
        "validation_errors": [],
        "is_valid": False,
        "stored_entities": 0,
        "stored_relationships": 0
    }
    
    # Run the graph
    try:
        await event_manager.publish(site_id, {"type": "log", "message": f"Starting acquisition for niche: {niche}"})
        
        # Use astream instead of stream for async
        async for output in graph.astream(state):
            if cancel_event.is_set():
                await event_manager.publish(site_id, {"type": "log", "message": "Workflow aborted by user."})
                break
                
            node_name = list(output.keys())[0]
            node_state = output[node_name]
            
            # Publish queue updates based on searcher output
            if node_name == "searcher":
                if "urls_to_scrape" in node_state:
                    queue_items = [{"url": url, "status": "queued", "type": "Web"} for url in node_state["urls_to_scrape"]]
                    await event_manager.publish(site_id, {"type": "queue", "data": queue_items})
                    
            # Publish real-time status updates for the current URL
            elif node_name == "scraper":
                if "current_url" in node_state and node_state["current_url"]:
                    await event_manager.publish(site_id, {
                        "type": "queue_update", 
                        "url": node_state["current_url"], 
                        "status": "extracting"
                    })
            elif node_name == "bouncer":
                if "current_url" in node_state and node_state["current_url"]:
                    # If it's not relevant, mark as failed (or rejected)
                    status = "evaluating" if node_state.get("is_relevant") else "failed"
                    await event_manager.publish(site_id, {
                        "type": "queue_update", 
                        "url": node_state["current_url"], 
                        "status": status
                    })
            elif node_name == "vector_storage":
                if "current_url" in node_state and node_state["current_url"]:
                    await event_manager.publish(site_id, {
                        "type": "queue_update", 
                        "url": node_state["current_url"], 
                        "status": "completed"
                    })
                stored_chunks = node_state.get('stored_chunks', 0)
                # We don't have new_data event for frontend Vault yet, it will be empty
                pass
                
        if not cancel_event.is_set():
            await event_manager.publish(site_id, {"type": "log", "message": "Workflow completed successfully."})
    except Exception as e:
        await event_manager.publish(site_id, {"type": "log", "message": f"Workflow failed: {str(e)}"})
        print(f"Workflow failed: {e}")
    finally:
        active_workflows.pop(site_id, None)
        await event_manager.publish(site_id, {"type": "status", "is_acquiring": False})

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
        "ignore_size_limit": True
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
        
    # 2. Bouncer
    state = await bouncer_node(state)
    
    if not state.get("is_relevant"):
        await event_manager.publish(site_id, {"type": "log", "message": f"[TargetedWorker] Document rejected by bouncer: {state.get('relevance_reason')}"})
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(PendingDocument).where(PendingDocument.id == doc_id))
            doc = result.scalars().first()
            if doc:
                doc.status = "rejected"
                await session.commit()
        return
        
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
        
    if doc.status != "pending":
        raise HTTPException(status_code=400, detail="Document is no longer pending")

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
        return {"message": "Cancellation requested"}
    
    return {"message": "No active workflow found"}

@router.post("/pipelines/{site_id}/generate-graph", status_code=202)
async def generate_graph(
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

    if site.graph_status in ["queued", "processing"]:
        return {"message": "Graph generation already running or queued"}

    site.graph_status = "queued"
    await db.commit()
    
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

    if site.graph_status in ["queued", "processing"]:
        site.graph_status = "cancelled"
        await db.commit()
        return {"message": "Graph generation cancellation requested"}
    
    return {"message": "No active graph generation workflow found"}

@router.get("/pipelines/{site_id}/entities")
async def get_pipeline_entities(
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

    entities = []
    relationships = []
    
    async with driver.session() as session:
        # Fetch Top 5000 Relationships and their connected nodes simultaneously
        result = await session.run(
            """
            MATCH (s:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH]->(t:CanonicalEntity {pipeline_id: $pipeline_id})
            RETURN id(s) as source_id, s.name as source_name, s.type as source_type, 
                   id(t) as target_id, t.name as target_name, t.type as target_type, 
                   r.type as rel_type, r.weight as weight, r.quotes as quotes
            ORDER BY r.weight DESC
            LIMIT 2500
            """, 
            pipeline_id=site_id
        )
        records = await result.data()
        
        unique_nodes = {}
        for record in records:
            # Add source node
            if record["source_id"] not in unique_nodes:
                unique_nodes[record["source_id"]] = {
                    "id": str(record["source_id"]),
                    "name": record["source_name"],
                    "type": record["source_type"],
                    "summary": None,
                    "source_url": None
                }
            # Add target node
            if record["target_id"] not in unique_nodes:
                unique_nodes[record["target_id"]] = {
                    "id": str(record["target_id"]),
                    "name": record["target_name"],
                    "type": record["target_type"],
                    "summary": None,
                    "source_url": None
                }
            
            # Add relationship
            relationships.append({
                "source": str(record["source_id"]),
                "source_name": record["source_name"],
                "type": record["rel_type"],
                "target": str(record["target_id"]),
                "target_name": record["target_name"],
                "weight": record["weight"],
                "quotes": record["quotes"] or []
            })
            
        entities = list(unique_nodes.values())

    return {"entities": entities, "relationships": relationships}

@router.get("/pipelines/{site_id}/nodes/{node_id}/explore")
async def explore_node_group(
    site_id: str,
    node_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    from src.db.neo4j_session import driver
    from langchain_google_genai import ChatGoogleGenerativeAI
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
                id(c) as central_id, c.name as central_name, c.type as central_type,
                id(n1) as neighbor_id, n1.name as neighbor_name, n1.type as neighbor_type,
                r1.type as rel_type, r1.weight as weight, r1.quotes as quotes, r1.source_urls as source_urls,
                startNode(r1) = c as is_outgoing
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
                        "type": record["neighbor_type"]
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
                    
        # Always generate a new investor insight
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash", 
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.0
        )
        
        # Format relationships for the prompt
        rels_text = []
        for r in relationships:
            direction = "->" if r["source"] == str(central_record["central_id"]) else "<-"
            other_node = r["target_name"] if r["source"] == str(central_record["central_id"]) else r["source_name"]
            quotes = " | ".join(r["quotes"][:3]) # Limit to top 3 quotes to save context
            
            # Filter out empty URLs
            valid_urls = [url for url in r.get("source_urls", []) if url and url.strip()]
            sources = ", ".join(valid_urls[:3])
            source_str = f" [Source: {sources}]" if sources else ""
            
            # If there are valid URLs, format them as markdown links immediately
            # so the LLM doesn't have to guess
            if valid_urls:
                formatted_sources = ", ".join([f"[{url}]({url})" for url in valid_urls[:3]])
                source_str = f" [Source: {formatted_sources}]"
                
            rels_text.append(f"- {central_node['name']} {direction} [{r['type']}] {direction} {other_node} (Evidence: \"{quotes}\"{source_str})")
            
        prompt = f"""You are a VC/PE analyst. Analyze this central entity and its network of relationships. 
Provide a holistic description of this group, the dynamics at play, and why it is relevant from an investment perspective.

Central Entity: {central_node['name']} ({central_node['type']})

Relationships:
{chr(10).join(rels_text)}

Provide a concise, insightful 2-3 paragraph analysis.
The relationships above already contain pre-formatted Markdown links in the `[Source: ...]` sections.
Whenever you mention a fact or relationship from the evidence, you MUST include the exact Markdown link provided in the relationship string. 
Do NOT try to create your own links. Just copy the `[URL](URL)` strings exactly as they appear in the Relationships section above.
If a relationship does not have a `[Source: ...]` section with a Markdown link, do not add a link for it."""

        try:
            insight_result = await llm.ainvoke(prompt)
            central_node["investor_insight"] = insight_result.content
        except Exception as e:
            print(f"Failed to generate investor insight: {e}")
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
            MATCH (cs:CanonicalEntity {pipeline_id: $pipeline_id})<-[:RESOLVES_TO]-(rs:RawEntity)
                  -[r:RAW_RELATIONSHIP]->
                  (rt:RawEntity)-[:RESOLVES_TO]->(ct:CanonicalEntity {pipeline_id: $pipeline_id})
            WITH id(cs) AS Source, id(ct) AS Target, r.type AS Label, count(r) as Weight
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
        raise HTTPException(status_code=403, detail="Not authorized")
        
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
