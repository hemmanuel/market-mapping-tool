from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
import json
import asyncio

from src.db.session import get_db_session
from src.models.relational import Tenant, Site, DataSource
from src.api.schemas import PipelineConfig
from src.api.auth import get_current_tenant
from src.agents.workflow import build_acquisition_graph
from src.api.events import event_manager

router = APIRouter()

async def run_acquisition_workflow(site_id: str, niche: str, ontology: dict):
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
            node_name = list(output.keys())[0]
            node_state = output[node_name]
            
            # Publish queue updates based on searcher output
            if node_name == "searcher":
                if "urls_to_scrape" in node_state:
                    queue_items = [{"url": url, "status": "queued", "type": "Web"} for url in node_state["urls_to_scrape"]]
                    await event_manager.publish(site_id, {"type": "queue", "data": queue_items})
            
            # Publish new data event to instantly update the frontend Vault
            elif node_name == "storage":
                if node_state.get('extracted_entities') or node_state.get('extracted_relationships'):
                    await event_manager.publish(site_id, {
                        "type": "new_data", 
                        "entities": node_state.get('extracted_entities', []), 
                        "relationships": node_state.get('extracted_relationships', [])
                    })
                
        await event_manager.publish(site_id, {"type": "log", "message": "Workflow completed successfully."})
    except Exception as e:
        await event_manager.publish(site_id, {"type": "log", "message": f"Workflow failed: {str(e)}"})
        print(f"Workflow failed: {e}")

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
    background_tasks.add_task(run_acquisition_workflow, str(site.id), site.name, site.ontology)
    
    return {"message": "Data acquisition started in background"}

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
        # Fetch entities
        result = await session.run("MATCH (n) WHERE n.pipeline_id = $pipeline_id RETURN n, labels(n) as labels LIMIT 100", pipeline_id=site_id)
        records = await result.data()
        for record in records:
            node = record["n"]
            labels = record["labels"]
            entities.append({
                "name": node.get("name"),
                "type": labels[0] if labels else "Unknown",
                "source_url": node.get("source_url")
            })
            
        # Fetch relationships
        result = await session.run("MATCH (s)-[r]->(t) WHERE r.pipeline_id = $pipeline_id RETURN s.name as source, type(r) as type, t.name as target LIMIT 100", pipeline_id=site_id)
        records = await result.data()
        for record in records:
            relationships.append({
                "source": record["source"],
                "type": record["type"],
                "target": record["target"]
            })

    return {"entities": entities, "relationships": relationships}

@router.post("/pipelines", status_code=201)
async def create_pipeline(
    config: PipelineConfig, 
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_tenant)
):
    # 1. Get or create the Tenant for the authenticated user
    result = await db.execute(select(Tenant).where(Tenant.auth_id == user_id))
    tenant = result.scalars().first()
    
    if not tenant:
        tenant = Tenant(name=f"Tenant for {user_id}", auth_id=user_id)
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

    # 2. Create a new Site for this niche
    if not config.niche:
        raise HTTPException(status_code=400, detail="Niche is required to create a pipeline.")

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
