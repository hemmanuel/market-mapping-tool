import asyncio
import os
import time
import json
import numpy as np
import requests
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.future import select
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_similarity

from vllm import LLM, SamplingParams

from src.db.session import AsyncSessionLocal
from src.db.neo4j_session import driver
from src.models.relational import DataSource, Document as PGDocument, Site

def publish_event(site_id: str, event_data: dict):
    try:
        # Send the event back to the FastAPI server
        requests.post(
            f"http://host.docker.internal:8000/api/v1/internal/events/{site_id}",
            json=event_data,
            timeout=1
        )
    except Exception as e:
        print(f"Failed to send event to API: {e}")

# Initialize LLMs
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key=os.getenv("GEMINI_API_KEY"))

class ExtractedEntity(BaseModel):
    name: str = Field(description="The name of the entity")
    type: str = Field(description="The type of the entity (e.g., Company, Person, Concept, Technology)")

class ExtractedRelationship(BaseModel):
    source: str = Field(description="The name of the source entity")
    target: str = Field(description="The name of the target entity")
    type: str = Field(description="The type of relationship (e.g., COMPETES_WITH, USES_TECHNOLOGY)")
    exact_quote: str = Field(description="The exact, verbatim substring from the text that proves this relationship exists")

class GraphExtraction(BaseModel):
    entities: List[ExtractedEntity] = Field(description="List of extracted entities")
    relationships: List[ExtractedRelationship] = Field(description="List of extracted relationships between entities")

class CanonicalEntity(BaseModel):
    canonical_name: str = Field(description="The canonical, standardized name for the cluster of entities")
    type: str = Field(description="The canonical type of the entity")
    raw_names: List[str] = Field(description="The raw entity names that belong to this canonical entity")

class CanonicalResolution(BaseModel):
    canonical_entities: List[CanonicalEntity] = Field(description="List of resolved canonical entities")

class AnchorSentences(BaseModel):
    sentences: List[str] = Field(description="List of 10 prototypical sentences")

async def generate_anchor_vectors(niche: str) -> List[str]:
    prompt = f"""You are an expert market analyst specializing in the {niche} sector. I am building a semantic search filter to find the most insight-dense sentences in a massive dataset of web scrapes.

Generate 10 highly distinct, prototypical sentences that represent the most valuable types of market intelligence in this specific industry. These sentences should cover:
1. Mergers, acquisitions, or investments.
2. Strategic partnerships or joint ventures.
3. Product launches or technological breakthroughs.
4. Regulatory approvals or government contracts.
5. Key personnel changes or leadership quotes.

Do not use real company names; use generic placeholders like 'Company A' or 'The Startup'. Make the sentence structures complex and realistic to business journalism."""
    
    structured_llm = llm.with_structured_output(AnchorSentences)
    result = await structured_llm.ainvoke(prompt)
    return result.sentences

async def run_graph_generation_worker(site_id: str, niche: str, vllm_engine: LLM):
    try:
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": 0,
            "current_phase": "Initialization",
            "message": "Starting offline batch graph generation worker..."
        })

        # 1. Fetch all chunks for the site
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(DataSource.id).where(DataSource.site_id == site_id))
            data_source_ids = result.scalars().all()
            
            if not data_source_ids:
                publish_event(site_id, {
                    "type": "graph_progress",
                    "processed_chunks": 0,
                    "total_chunks": 0,
                    "current_phase": "Error",
                    "message": "No data sources found for this pipeline."
                })
                return

            result = await session.execute(
                select(PGDocument).where(PGDocument.data_source_id.in_(data_source_ids))
            )
            documents = result.scalars().all()

        total_raw_chunks = len(documents)
        if total_raw_chunks == 0:
            publish_event(site_id, {
                "type": "graph_progress",
                "processed_chunks": 0,
                "total_chunks": 0,
                "current_phase": "Error",
                "message": "No chunks found to process."
            })
            return

        # Stage 1: Semantic Funnel (Filtering)
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": total_raw_chunks,
            "current_phase": "Stage 1: Semantic Funnel",
            "message": f"Generating anchor vectors for niche: {niche}..."
        })
        
        anchors = await generate_anchor_vectors(niche)
        
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": total_raw_chunks,
            "current_phase": "Stage 1: Semantic Funnel",
            "message": f"Embedding {total_raw_chunks} chunks for semantic filtering..."
        })
        
        model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
        anchor_embeddings = model.encode(anchors)
        
        doc_texts = [doc.raw_text for doc in documents]
        doc_embeddings = model.encode(doc_texts, show_progress_bar=False)
        
        similarities = cosine_similarity(doc_embeddings, anchor_embeddings)
        max_similarities = similarities.max(axis=1)
        
        THRESHOLD = 0.35
        filtered_documents = []
        for i, doc in enumerate(documents):
            if max_similarities[i] >= THRESHOLD:
                filtered_documents.append(doc)
                
        total_chunks = len(filtered_documents)
        print(f"Semantic Funnel: Kept {total_chunks} out of {total_raw_chunks} chunks.")

        if total_chunks == 0:
            publish_event(site_id, {
                "type": "graph_progress",
                "processed_chunks": 0,
                "total_chunks": total_raw_chunks,
                "current_phase": "Error",
                "message": "Semantic Funnel filtered out all chunks. No data left to process."
            })
            return

        # Phase 1: Raw Extraction (Using Offline vLLM Engine)
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": total_chunks,
            "current_phase": "Phase 1: Raw Extraction",
            "message": f"Semantic Funnel kept {total_chunks}/{total_raw_chunks} chunks. Starting offline OpenIE extraction..."
        })

        # Ensure Neo4j indexes exist for fast MERGE operations
        async with driver.session() as neo4j_session:
            await neo4j_session.run("CREATE INDEX IF NOT EXISTS FOR (e:RawEntity) ON (e.name, e.pipeline_id)")
            await neo4j_session.run("CREATE INDEX IF NOT EXISTS FOR (c:CanonicalEntity) ON (c.name, c.pipeline_id)")
            await neo4j_session.run("CREATE INDEX IF NOT EXISTS FOR (comm:Community) ON (comm.id, comm.pipeline_id)")

        schema = GraphExtraction.model_json_schema()
        system_prompt = """You are an Open Information Extraction system. Read the text and extract every distinct entity (people, companies, concepts, technologies, regulations, metrics, etc.). For every pair of entities that interact, extract the relationship between them. Name the entity types and relationship types whatever you think is most accurate. Do not constrain yourself to a specific schema.

CRITICAL: For every relationship, you MUST extract the exact, verbatim substring from the text that proves this relationship exists in the `exact_quote` field. If you cannot quote the text verbatim, do not extract the relationship.

You MUST respond in valid JSON format matching this exact schema:
{
  "entities": [{"name": "string", "type": "string"}],
  "relationships": [{"source": "string", "target": "string", "type": "string", "exact_quote": "string"}]
}"""

        prompts = []
        for doc in filtered_documents:
            # Format as chat messages for the model
            chat_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Text:\n{doc.raw_text}"}
            ]
            # Since vLLM offline engine needs formatted prompts, we can use the tokenizer's apply_chat_template if available
            # or just format it manually if using a specific model. Hermes uses ChatML.
            # We'll rely on vllm's built-in chat template support if possible, or format manually.
            # For simplicity, we'll format it manually for Hermes-3-Llama-3.1-8B (ChatML)
            formatted_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\nText:\n{doc.raw_text}<|im_end|>\n<|im_start|>assistant\n"
            prompts.append(formatted_prompt)

        sampling_params = SamplingParams(
            temperature=0.0,
            max_tokens=4096
        )

        start_time = time.time()
        
        batch_size = 500
        processed_count = 0
        
        import re
        def clean_json_string(raw_str: str) -> str:
            s = raw_str.strip()
            # Remove markdown code block syntax
            s = re.sub(r'^```(?:json)?\s*', '', s)
            s = re.sub(r'\s*```$', '', s)
            s = s.strip()
            
            # Find the first '{' and the last '}'
            start_idx = s.find('{')
            end_idx = s.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                s = s[start_idx:end_idx+1]
                
            # Fix common unescaped control characters that break json.loads
            s = re.sub(r'[\x00-\x1f]', '', s)
            return s

        for i in range(0, len(prompts), batch_size):
            batch_prompts = prompts[i:i+batch_size]
            batch_docs = filtered_documents[i:i+batch_size]
            
            # Run offline batch inference for this sub-batch
            outputs = await asyncio.to_thread(vllm_engine.generate, batch_prompts, sampling_params)
            
            batch_entities = []
            batch_relationships = []
            
            for j, output in enumerate(outputs):
                doc = batch_docs[j]
                content = output.outputs[0].text
                
                if not content or not content.strip():
                    continue
                    
                content = clean_json_string(content)
                
                source_url = None
                if isinstance(doc.metadata_json, dict):
                    source_url = doc.metadata_json.get("source_url")
                elif isinstance(doc.metadata_json, str):
                    try:
                        meta_dict = json.loads(doc.metadata_json)
                        if isinstance(meta_dict, dict):
                            source_url = meta_dict.get("source_url")
                    except:
                        pass

                try:
                    parsed = json.loads(content)
                    entities = parsed.get("entities", [])
                    relationships = parsed.get("relationships", [])
                    
                    if isinstance(entities, list):
                        for e in entities:
                            if isinstance(e, dict):
                                name = e.get("name")
                                type_ = e.get("type")
                                if isinstance(name, str) and isinstance(type_, str):
                                    batch_entities.append({
                                        "name": name, "type": type_, "source_url": source_url
                                    })
                                    
                    if isinstance(relationships, list):
                        for r in relationships:
                            if isinstance(r, dict):
                                source = r.get("source")
                                target = r.get("target")
                                rel_type = r.get("type")
                                exact_quote = r.get("exact_quote", "")
                                
                                if isinstance(source, str) and isinstance(target, str) and isinstance(rel_type, str):
                                    batch_relationships.append({
                                        "source": source, "target": target, "type": rel_type,
                                        "exact_quote": str(exact_quote) if exact_quote else "", "source_url": source_url
                                    })
                except Exception as e:
                    print(f"Error parsing/validating JSON for chunk {doc.id}: {e}")

            # Write to Neo4j for this sub-batch
            async with driver.session() as neo4j_session:
                write_chunk_size = 1000
                for k in range(0, len(batch_entities), write_chunk_size):
                    await neo4j_session.run(
                        """
                        UNWIND $entities AS entity
                        MERGE (e:RawEntity {name: entity.name, pipeline_id: $pipeline_id})
                        SET e.type = entity.type, e.source_url = entity.source_url
                        """,
                        entities=batch_entities[k:k+write_chunk_size],
                        pipeline_id=site_id
                    )
                for k in range(0, len(batch_relationships), write_chunk_size):
                    await neo4j_session.run(
                        """
                        UNWIND $relationships AS rel
                        MERGE (s:RawEntity {name: rel.source, pipeline_id: $pipeline_id})
                        MERGE (t:RawEntity {name: rel.target, pipeline_id: $pipeline_id})
                        MERGE (s)-[r:RAW_RELATIONSHIP {type: rel.type, pipeline_id: $pipeline_id}]->(t)
                        SET r.exact_quote = rel.exact_quote, r.source_url = rel.source_url
                        """,
                        relationships=batch_relationships[k:k+write_chunk_size],
                        pipeline_id=site_id
                    )
            
            processed_count += len(batch_prompts)
            
            publish_event(site_id, {
                "type": "graph_progress",
                "processed_chunks": processed_count,
                "total_chunks": total_chunks,
                "current_phase": "Phase 1: Raw Extraction",
                "message": f"Processed {processed_count}/{total_chunks} chunks."
            })
            
        elapsed = time.time() - start_time
        print(f"Offline batch inference completed in {elapsed:.2f}s")

        # Phase 2: Canonical Resolution (Using Vector Embeddings + DBSCAN)
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 2: Canonical Resolution",
            "message": "Fetching raw entities for clustering..."
        })

        async with driver.session() as neo4j_session:
            result = await neo4j_session.run(
                "MATCH (e:RawEntity {pipeline_id: $pipeline_id}) RETURN e.name as name, e.type as type",
                pipeline_id=site_id
            )
            records = await result.data()
            raw_entities = [{"name": r["name"], "type": r["type"]} for r in records]

        if not raw_entities:
            publish_event(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Complete",
                "message": "No entities extracted. Graph generation complete."
            })
            return

        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 2: Canonical Resolution",
            "message": f"Embedding and clustering {len(raw_entities)} raw entities..."
        })

        # Embed entities
        model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
        entity_names = [e["name"] for e in raw_entities]
        embeddings = model.encode(entity_names, show_progress_bar=False)

        # Cluster using DBSCAN
        clustering = DBSCAN(eps=0.15, min_samples=1, metric='cosine').fit(embeddings)
        labels = clustering.labels_

        # Group entities by cluster
        clusters = {}
        for i, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(raw_entities[i])

        # Write to Neo4j
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 2: Canonical Resolution",
            "message": f"Writing {len(clusters)} canonical entities to database..."
        })

        async with driver.session() as neo4j_session:
            for label, cluster_entities in clusters.items():
                canonical_name = sorted(cluster_entities, key=lambda x: len(x["name"]))[0]["name"]
                types = [e["type"] for e in cluster_entities if e["type"]]
                canonical_type = max(set(types), key=types.count) if types else "Unknown"

                await neo4j_session.run(
                    """
                    MERGE (c:CanonicalEntity {name: $canonical_name, pipeline_id: $pipeline_id})
                    SET c.type = $type
                    """,
                    canonical_name=canonical_name,
                    type=canonical_type,
                    pipeline_id=site_id
                )
                
                raw_names = list(set([e["name"] for e in cluster_entities]))
                for raw_name in raw_names:
                    await neo4j_session.run(
                        """
                        MATCH (r:RawEntity {name: $raw_name, pipeline_id: $pipeline_id})
                        MATCH (c:CanonicalEntity {name: $canonical_name, pipeline_id: $pipeline_id})
                        MERGE (r)-[:RESOLVES_TO]->(c)
                        """,
                        raw_name=raw_name,
                        canonical_name=canonical_name,
                        pipeline_id=site_id
                    )

        # Phase 3: GraphRAG Community Detection
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 3: Community Detection",
            "message": "Running Louvain community detection..."
        })

        async with driver.session() as neo4j_session:
            graph_name = f"graph_{site_id.replace('-', '_')}"
            
            await neo4j_session.run(f"CALL gds.graph.drop('{graph_name}', false)")
            
            await neo4j_session.run(
                f"""
                CALL gds.graph.project.cypher(
                  '{graph_name}',
                  'MATCH (n:CanonicalEntity {{pipeline_id: "{site_id}"}}) RETURN id(n) AS id',
                  'MATCH (s:CanonicalEntity {{pipeline_id: "{site_id}"}})<-[:RESOLVES_TO]-(:RawEntity)-[:RAW_RELATIONSHIP]->(:RawEntity)-[:RESOLVES_TO]->(t:CanonicalEntity {{pipeline_id: "{site_id}"}})
                   RETURN id(s) AS source, id(t) AS target'
                )
                """
            )
            
            await neo4j_session.run(
                f"""
                CALL gds.louvain.write('{graph_name}', {{ writeProperty: 'community_id' }})
                """
            )
            
            publish_event(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Phase 3: Community Detection",
                "message": "Generating community summaries with Gemini..."
            })
            
            result = await neo4j_session.run(
                """
                MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
                WITH c.community_id AS community_id, collect(c.name) AS entities
                RETURN community_id, entities
                """,
                pipeline_id=site_id
            )
            communities = await result.data()
            
            await neo4j_session.run(f"CALL gds.graph.drop('{graph_name}', false)")

            for comm in communities:
                community_id = comm["community_id"]
                entities = comm["entities"]
                
                if len(entities) < 3:
                    continue
                    
                prompt = f"You are a market analyst. Look at this list of entities that form a distinct cluster in a market graph. Provide a short, 3-5 word descriptive name for this sector, and a 1-2 sentence summary of what this sector represents.\n\nEntities: {', '.join(entities[:50])}"
                
                try:
                    summary_result = await llm.ainvoke(prompt)
                    summary_text = summary_result.content
                    
                    await neo4j_session.run(
                        """
                        MERGE (comm:Community {id: $community_id, pipeline_id: $pipeline_id})
                        SET comm.summary = $summary, comm.name = $name
                        WITH comm
                        MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id, community_id: $community_id})
                        MERGE (c)-[:BELONGS_TO]->(comm)
                        """,
                        community_id=str(community_id),
                        pipeline_id=site_id,
                        summary=summary_text,
                        name=f"Sector {community_id}"
                    )
                except Exception as e:
                    print(f"Error generating summary for community {community_id}: {e}")

        # Phase 4: Edge Collapsing (Building the Market Map)
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 4: Edge Collapsing",
            "message": "Building direct relationships between canonical entities..."
        })

        async with driver.session() as neo4j_session:
            await neo4j_session.run(
                """
                MATCH (cs:CanonicalEntity {pipeline_id: $pipeline_id})<-[:RESOLVES_TO]-(rs:RawEntity)-[r:RAW_RELATIONSHIP]->(rt:RawEntity)-[:RESOLVES_TO]->(ct:CanonicalEntity {pipeline_id: $pipeline_id})
                WHERE cs <> ct
                WITH cs, ct, r.type AS rel_type, count(r) AS weight, collect(r.exact_quote) AS quotes, collect(r.source_url) AS source_urls
                MERGE (cs)-[rel:INTERACTS_WITH {type: rel_type, pipeline_id: $pipeline_id}]->(ct)
                SET rel.weight = weight, 
                    rel.quotes = [q IN quotes WHERE q IS NOT NULL AND q <> ""],
                    rel.source_urls = [url IN source_urls WHERE url IS NOT NULL AND url <> ""]
                """,
                pipeline_id=site_id
            )

        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Complete",
            "message": "Graph generation completed successfully!"
        })

    except Exception as e:
        print(f"Graph generation failed: {e}")
        publish_event(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": 0,
            "current_phase": "Error",
            "message": f"Graph generation failed: {str(e)}"
        })

async def poll_for_jobs():
    print("Starting GPU Worker polling...")
    
    # Initialize vLLM engine once
    print("Initializing vLLM Engine...")
    vllm_engine = LLM(
        model="NousResearch/Hermes-3-Llama-3.1-8B",
        max_model_len=8192,
        gpu_memory_utilization=0.90,
        max_num_seqs=1024
    )
    print("vLLM Engine initialized.")

    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Find a queued job
                result = await session.execute(
                    select(Site).where(Site.graph_status == "queued").limit(1)
                )
                site = result.scalars().first()

                if site:
                    print(f"Found queued job for site: {site.name} ({site.id})")
                    # Mark as processing
                    site.graph_status = "processing"
                    await session.commit()
                    
                    # Run the job
                    await run_graph_generation_worker(str(site.id), site.name, vllm_engine)
                    
                    # Mark as complete (or idle)
                    site.graph_status = "idle"
                    await session.commit()
                    print(f"Job complete for site: {site.name}")
                else:
                    # No jobs, sleep
                    await asyncio.sleep(10)
        except Exception as e:
            print(f"Error in polling loop: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(poll_for_jobs())
