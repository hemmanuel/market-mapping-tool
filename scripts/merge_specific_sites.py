import asyncio
from sqlalchemy.future import select
from sqlalchemy import func
from src.db.session import AsyncSessionLocal
from src.models.relational import Tenant, Site, DataSource

async def merge_ep():
    async with AsyncSessionLocal() as session:
        # Get all tenants
        result = await session.execute(select(Tenant))
        tenants = result.scalars().all()
        
        for tenant in tenants:
            print(f"Processing tenant: {tenant.auth_id}")
            # Get all sites for this tenant
            result = await session.execute(
                select(Site).where(Site.tenant_id == tenant.id).order_by(Site.created_at.asc())
            )
            sites = result.scalars().all()
            
            # Find the two targets
            target_1 = None
            target_2 = None
            
            for site in sites:
                name_lower = site.name.lower()
                if name_lower == "exploration and production (e&p)":
                    target_1 = site
                elif name_lower == "exploration & production (e&p)":
                    target_2 = site
                    
            if target_1 and target_2:
                print(f"Found both targets to merge.")
                # We'll keep target_2 as master ("Exploration & Production (E&P)")
                master_site = target_2
                duplicate_site = target_1
                
                print(f"Master site ID: {master_site.id} ({master_site.name})")
                print(f"Merging duplicate site ID: {duplicate_site.id} ({duplicate_site.name})")
                
                # Reassign DataSources
                result = await session.execute(
                    select(DataSource).where(DataSource.site_id == duplicate_site.id)
                )
                data_sources = result.scalars().all()
                for ds in data_sources:
                    ds.site_id = master_site.id
                
                # Flush to ensure reassignment is registered before deletion
                await session.flush()
                
                # Delete duplicate site
                await session.delete(duplicate_site)
                
                await session.commit()
                print("Committed changes.")
            else:
                print("Did not find both targets for this tenant.")
            
if __name__ == "__main__":
    asyncio.run(merge_ep())