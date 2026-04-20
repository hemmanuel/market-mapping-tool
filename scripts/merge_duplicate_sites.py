import asyncio
from sqlalchemy.future import select
from sqlalchemy import func
from src.db.session import AsyncSessionLocal
from src.models.relational import Tenant, Site, DataSource

async def main():
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
            
            # Group by lower(name)
            sites_by_name = {}
            for site in sites:
                name_key = site.name.lower()
                if name_key not in sites_by_name:
                    sites_by_name[name_key] = []
                sites_by_name[name_key].append(site)
                
            for name_key, site_list in sites_by_name.items():
                if len(site_list) > 1:
                    print(f"  Found {len(site_list)} sites for '{name_key}'")
                    master_site = site_list[0]
                    duplicate_sites = site_list[1:]
                    
                    print(f"    Master site ID: {master_site.id}")
                    for dup in duplicate_sites:
                        print(f"    Merging duplicate site ID: {dup.id}")
                        # Reassign DataSources
                        result = await session.execute(
                            select(DataSource).where(DataSource.site_id == dup.id)
                        )
                        data_sources = result.scalars().all()
                        for ds in data_sources:
                            ds.site_id = master_site.id
                        
                        # Delete duplicate site
                        await session.delete(dup)
                        
        await session.commit()
        print("Committed changes.")
            
if __name__ == "__main__":
    asyncio.run(main())