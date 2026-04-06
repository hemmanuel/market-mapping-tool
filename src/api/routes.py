from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.db.session import get_db_session
from src.models.relational import Tenant, Site, DataSource
from src.api.schemas import PipelineConfig
from src.api.auth import get_current_tenant

router = APIRouter()

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
