import asyncio
import sys
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Add the project root to the Python path
sys.path.append('/app')

from sqlalchemy.future import select
from src.db.session import AsyncSessionLocal
from src.db.neo4j_session import driver
from src.models.relational import Document as PGDocument, DataSource

async def generate_semantic_edges():
    print("Starting True RAG Semantic Edge Generation...")
    
    print("Fetching document chunks and their pgvector embeddings from PostgreSQL...")
    async with AsyncSessionLocal() as session:
        # Fetch chunks that have embeddings
        result = await session.execute(
            select(PGDocument.embedding, PGDocument.metadata_json, DataSource.site_id)
            .join(DataSource, PGDocument.data_source_id == DataSource.id)
            .where(PGDocument.embedding.is_not(None))
        )
        records = result.all()
        
    if not records:
        print("No document chunks with embeddings found.")
        return

    print(f"Found {len(records)} chunks with embeddings. Grouping by site_id and source_url...")
    
    # Group by site_id -> source_url -> list of embeddings
    site_docs = {}
    for embedding, metadata_json, site_id in records:
        if not isinstance(metadata_json, dict):
            continue
        source_url = metadata_json.get("source_url")
        if not source_url:
            continue
            
        if site_id not in site_docs:
            site_docs[site_id] = {}
        if source_url not in site_docs[site_id]:
            site_docs[site_id][source_url] = []
            
        # Convert pgvector (usually list of floats) to numpy array
        site_docs[site_id][source_url].append(np.array(embedding))
        
    for site_id, url_embeddings in site_docs.items():
        urls = list(url_embeddings.keys())
        if len(urls) < 2:
            continue
            
        print(f"Processing {len(urls)} unique documents for site {site_id}...")
        
        edges = []
        threshold = 0.85
        
        # Compare every pair of documents
        for i in range(len(urls)):
            url_a = urls[i]
            chunks_a = np.array(url_embeddings[url_a]) # Shape: (num_chunks_a, embedding_dim)
            
            for j in range(i + 1, len(urls)):
                url_b = urls[j]
                chunks_b = np.array(url_embeddings[url_b]) # Shape: (num_chunks_b, embedding_dim)
                
                # Compute cosine similarity between all chunks of A and all chunks of B
                # Resulting matrix shape: (num_chunks_a, num_chunks_b)
                sim_matrix = cosine_similarity(chunks_a, chunks_b)
                
                # Find the maximum similarity between any chunk in A and any chunk in B
                max_sim = float(np.max(sim_matrix))
                
                if max_sim > threshold:
                    edges.append({
                        "source": url_a,
                        "target": url_b,
                        "weight": max_sim
                    })
                    
        print(f"Found {len(edges)} chunk-level SIMILAR_TO edges for site {site_id}.")
        
        if edges:
            # Batch insert edges into Neo4j
            batch_size = 1000
            async with driver.session() as neo4j_session:
                for idx in range(0, len(edges), batch_size):
                    batch = edges[idx:idx + batch_size]
                    await neo4j_session.run(
                        """
                        UNWIND $batch AS edge
                        MATCH (d1:Document {url: edge.source, pipeline_id: $pipeline_id})
                        MATCH (d2:Document {url: edge.target, pipeline_id: $pipeline_id})
                        MERGE (d1)-[r:SIMILAR_TO]->(d2)
                        SET r.weight = edge.weight
                        """,
                        batch=batch,
                        pipeline_id=str(site_id)
                    )
            print(f"Successfully inserted {len(edges)} SIMILAR_TO edges into Neo4j for site {site_id}.")

    print("Finished True RAG Semantic Edge Generation.")

if __name__ == "__main__":
    asyncio.run(generate_semantic_edges())