import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.append('/app')

from sqlalchemy.future import select
from src.db.session import AsyncSessionLocal
from src.db.neo4j_session import driver
from src.models.relational import Document as PGDocument, DataSource

async def add_document_nodes():
    print("Starting to add Document nodes and MENTIONS edges to Neo4j...")
    
    async with AsyncSessionLocal() as session:
        # Fetch only needed fields to avoid OOM
        result = await session.execute(
            select(PGDocument.id, PGDocument.title, PGDocument.metadata_json, DataSource.site_id)
            .join(DataSource, PGDocument.data_source_id == DataSource.id)
        )
        records = result.all()
        
    if not records:
        print("No documents found in PostgreSQL.")
        return

    print(f"Found {len(records)} chunks in PostgreSQL. Grouping by unique source_url...")

    # Deduplicate by source_url to avoid redundant MERGEs
    unique_docs = {}
    for doc_id, title, metadata_json, site_id in records:
        source_url = None
        if isinstance(metadata_json, dict):
            source_url = metadata_json.get("source_url")
        
        if not source_url:
            continue

        if source_url not in unique_docs:
            # Determine type from extension or default to html
            doc_type = "html"
            if source_url.lower().endswith(".pdf"):
                doc_type = "pdf"
            elif source_url.lower().endswith(".docx"):
                doc_type = "docx"
            elif source_url.lower().endswith(".pptx"):
                doc_type = "pptx"
            elif source_url.lower().endswith(".xlsx") or source_url.lower().endswith(".csv"):
                doc_type = "spreadsheet"

            unique_docs[source_url] = {
                "url": source_url,
                "pipeline_id": str(site_id),
                "doc_id": str(doc_id),
                "title": title or source_url,
                "type": doc_type
            }

    docs_list = list(unique_docs.values())
    print(f"Found {len(docs_list)} unique documents. Batch inserting to Neo4j...")

    batch_size = 100
    async with driver.session() as neo4j_session:
        for i in range(0, len(docs_list), batch_size):
            batch = docs_list[i:i+batch_size]
            
            # 1. Create Document nodes
            await neo4j_session.run(
                """
                UNWIND $batch AS doc
                MERGE (d:Document {url: doc.url, pipeline_id: doc.pipeline_id})
                SET d.id = doc.doc_id, d.title = doc.title, d.type = doc.type
                """,
                batch=batch
            )

            # 2. Create MENTIONS edges from CanonicalEntities directly extracted from this source_url
            await neo4j_session.run(
                """
                UNWIND $batch AS doc
                MATCH (d:Document {url: doc.url, pipeline_id: doc.pipeline_id})
                MATCH (r:RawEntity {source_url: doc.url, pipeline_id: doc.pipeline_id})-[:RESOLVES_TO]->(c:CanonicalEntity {pipeline_id: doc.pipeline_id})
                MERGE (d)-[:MENTIONS]->(c)
                """,
                batch=batch
            )
            
            # 3. Create MENTIONS edges from RAW_RELATIONSHIP source_urls
            await neo4j_session.run(
                """
                UNWIND $batch AS doc
                MATCH (d:Document {url: doc.url, pipeline_id: doc.pipeline_id})
                MATCH (s:RawEntity)-[rel:RAW_RELATIONSHIP {source_url: doc.url, pipeline_id: doc.pipeline_id}]->(t:RawEntity)
                MATCH (s)-[:RESOLVES_TO]->(cs:CanonicalEntity)
                MATCH (t)-[:RESOLVES_TO]->(ct:CanonicalEntity)
                MERGE (d)-[:MENTIONS]->(cs)
                MERGE (d)-[:MENTIONS]->(ct)
                """,
                batch=batch
            )
            print(f"Processed batch {i//batch_size + 1}/{(len(docs_list)-1)//batch_size + 1}")

    print("Finished adding Document nodes and MENTIONS edges.")

if __name__ == "__main__":
    asyncio.run(add_document_nodes())
