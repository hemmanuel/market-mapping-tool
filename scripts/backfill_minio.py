import asyncio
import os
import sys
import uuid
import httpx
import tempfile

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.future import select
from sqlalchemy.orm.attributes import flag_modified
from src.db.session import AsyncSessionLocal
from src.models.relational import Site, DataSource, Document as PGDocument
from src.services.storage import storage

SKIP_DOMAINS = [
    "bloomberg.com", "wsj.com", "forbes.com", "businesswire.com", 
    "linkedin.com", "ft.com", "sec.gov", "spglobal.com", 
    "pitchbook.com", "reuters.com", "cnbc.com", "nytimes.com"
]

async def backfill_site(site_name: str):
    print(f"Starting MinIO backfill for site: {site_name}")
    
    # Ensure bucket exists
    storage.ensure_bucket_exists()

    async with AsyncSessionLocal() as session:
        # 1. Find the Site
        result = await session.execute(select(Site).where(Site.name == site_name))
        site = result.scalars().first()
        
        if not site:
            print(f"Site '{site_name}' not found.")
            return

        # 2. Get Data Sources
        result = await session.execute(select(DataSource.id).where(DataSource.site_id == site.id))
        ds_ids = result.scalars().all()
        
        if not ds_ids:
            print("No data sources found for this site.")
            return

        # 3. Get unique URLs that need backfilling
        result = await session.execute(
            select(PGDocument)
            .where(PGDocument.data_source_id.in_(ds_ids))
        )
        
        docs = result.scalars().all()
        unique_urls = set()
        docs_by_url = {}
        
        for doc in docs:
            meta = doc.metadata_json
            if meta and "source_url" in meta and "storage_object" not in meta:
                url = meta["source_url"]
                unique_urls.add(url)
                if url not in docs_by_url:
                    docs_by_url[url] = []
                docs_by_url[url].append(doc)

        print(f"Found {len(unique_urls)} unique URLs to backfill.")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # 4. Process each URL
        async with httpx.AsyncClient() as client:
            for url in unique_urls:
                print(f"Processing: {url}")
                
                if any(domain in url.lower() for domain in SKIP_DOMAINS):
                    print(f"  -> Skipping known problematic domain.")
                    continue
                    
                try:
                    # Download the file
                    is_jina_fallback = False
                    try:
                        response = await client.get(url, headers=headers, timeout=15.0, follow_redirects=True)
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code in (401, 403):
                            print(f"  -> 403 Forbidden. Using Jina fallback...")
                            response = await client.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30.0, follow_redirects=True)
                            response.raise_for_status()
                            is_jina_fallback = True
                        else:
                            raise e
                    
                    content_type = response.headers.get("Content-Type", "").lower()
                    storage_object = None
                    
                    # Upload based on type
                    if is_jina_fallback:
                        storage_object = f"{site.id}/{uuid.uuid4()}.html"
                        storage.upload_text(response.text, storage_object, "text/html")
                    elif "application/pdf" in content_type or url.lower().endswith(".pdf"):
                        storage_object = f"{site.id}/{uuid.uuid4()}.pdf"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp.write(response.content)
                            tmp_path = tmp.name
                        try:
                            storage.upload_file(tmp_path, storage_object, "application/pdf")
                        finally:
                            os.unlink(tmp_path)
                    elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type or url.lower().endswith(".docx"):
                        storage_object = f"{site.id}/{uuid.uuid4()}.docx"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                            tmp.write(response.content)
                            tmp_path = tmp.name
                        try:
                            storage.upload_file(tmp_path, storage_object, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                        finally:
                            os.unlink(tmp_path)
                    else:
                        # Default to HTML
                        storage_object = f"{site.id}/{uuid.uuid4()}.html"
                        storage.upload_text(response.text, storage_object, "text/html")

                    # 5. Update the database metadata for all chunks with this URL
                    if storage_object:
                        print(f"  -> Uploaded to MinIO: {storage_object}")
                        
                        docs_to_update = docs_by_url[url]
                        for doc in docs_to_update:
                            new_meta = dict(doc.metadata_json)
                            new_meta["storage_object"] = storage_object
                            doc.metadata_json = new_meta
                            flag_modified(doc, "metadata_json")
                            
                        await session.commit()
                        print(f"  -> Updated {len(docs_to_update)} chunks in database.")

                except Exception as e:
                    print(f"  -> Failed to process {url}: {e}")
                    await session.rollback()

if __name__ == "__main__":
    target_site = sys.argv[1] if len(sys.argv) > 1 else "E&P Private Equity"
    asyncio.run(backfill_site(target_site))
