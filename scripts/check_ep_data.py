import asyncio
from sqlalchemy.future import select
from sqlalchemy import func
from src.db.session import AsyncSessionLocal
from src.models.relational import Site, DataSource, Document

async def check():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Site).where(Site.name.ilike('%e&p%')))
        sites = res.scalars().all()
        
        for site in sites:
            print(f"Site: {site.name} (ID: {site.id})")
            ds_res = await session.execute(select(DataSource).where(DataSource.site_id == site.id))
            data_sources = ds_res.scalars().all()
            print(f"  DataSources count: {len(data_sources)}")
            
            ds_ids = [ds.id for ds in data_sources]
            if not ds_ids:
                print("  No data sources.")
                continue
            
            doc_res = await session.execute(select(func.count()).select_from(Document).where(Document.data_source_id.in_(ds_ids)))
            count = doc_res.scalar()
            print(f"  Total chunks: {count}")
            
            if count > 0:
                sample_res = await session.execute(
                    select(Document)
                    .where(Document.data_source_id.in_(ds_ids))
                    .order_by(Document.processed_at.desc())
                    .limit(2)
                )
                samples = sample_res.scalars().all()
                for i, doc in enumerate(samples):
                    url = doc.metadata_json.get('source_url', 'N/A') if doc.metadata_json else 'N/A'
                    print(f"  --- Sample {i+1} ---")
                    print(f"  Processed At: {doc.processed_at}")
                    print(f"  Source URL: {url}")
                    text_snippet = doc.raw_text[:150].replace('\n', ' ')
                    print(f"  Text Snippet: {text_snippet}...")
            print("")

if __name__ == '__main__':
    asyncio.run(check())