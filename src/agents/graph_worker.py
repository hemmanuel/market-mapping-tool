import asyncio
import os
import time
import json
import aiohttp
import numpy as np
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.future import select
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_similarity

from src.db.session import AsyncSessionLocal
from src.db.neo4j_session import driver
from src.models.relational import DataSource, Document as PGDocument
from src.api.events import event_manager

# Initialize LLMs
llm = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"), api_key=os.getenv("GEMINI_API_KEY"))

class ExtractedEntity(BaseModel):
    name: str = Field(description="The name of the entity")
    type: str = Field(description="The type of the entity (e.g., Company, Person, Concept, Technology)")
    description: str = Field(description="A concise description or context of the entity based on the text")

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


async def llm_producer_worker(
    worker_id: int,
    task_queue: asyncio.Queue,
    results_queue: asyncio.Queue,
    http_session: aiohttp.ClientSession,
    cancel_event: asyncio.Event
):
    while not cancel_event.is_set():
        try:
            doc, site_id = task_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        start_time = time.time()
        try:
            schema = GraphExtraction.model_json_schema()
            system_prompt = """You are an Open Information Extraction system. Read the text and extract every distinct entity (people, companies, concepts, technologies, regulations, metrics, etc.). For every pair of entities that interact, extract the relationship between them. Name the entity types and relationship types whatever you think is most accurate. Do not constrain yourself to a specific schema.

CRITICAL: For every relationship, you MUST extract the exact, verbatim substring from the text that proves this relationship exists in the `exact_quote` field. If you cannot quote the text verbatim, do not extract the relationship.
CRITICAL: For every entity, you MUST extract a concise `description` or context of what the entity is, based on the text.

You MUST respond in valid JSON format matching this exact schema:
{
  "entities": [{"name": "string", "type": "string", "description": "string"}],
  "relationships": [{"source": "string", "target": "string", "type": "string", "exact_quote": "string"}]
}"""
            payload = {
                "model": "NousResearch/Hermes-3-Llama-3.1-8B",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Text:\n{doc.raw_text}"}
                ],
                "temperature": 0,
                "max_tokens": 4096,
                "extra_body": {"guided_json": schema}
            }
            
            async with http_session.post("http://localhost:8001/v1/chat/completions", json=payload, timeout=600.0) as response:
                response.raise_for_status()
                data = await response.json()
                content = data["choices"][0]["message"].get("content", "")
                
            if not content or not content.strip():
                print(f"[Worker {worker_id}] Chunk {doc.id} returned empty content.")
                content = '{"entities": [], "relationships": []}'
                
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

            # Put raw content into results queue for the consumer to parse and write
            await results_queue.put({
                "doc_id": doc.id,
                "site_id": site_id,
                "content": content,
                "source_url": source_url
            })
            
            elapsed = time.time() - start_time
            print(f"[Worker {worker_id}] Chunk {doc.id} processed in {elapsed:.2f}s")
        except asyncio.TimeoutError:
            print(f"[Worker {worker_id}] Timeout extracting from chunk {doc.id}")
        except Exception as e:
            print(f"[Worker {worker_id}] Error extracting from chunk {doc.id}: {e}")
        finally:
            task_queue.task_done()


async def neo4j_batch_consumer(
    results_queue: asyncio.Queue,
    total_chunks: int,
    site_id: str,
    cancel_event: asyncio.Event
):
    processed = 0
    batch_entities = []
    batch_relationships = []
    batch_size = 500
    last_write_time = time.time()
    
    while processed < total_chunks and not cancel_event.is_set():
        try:
            # Wait for a result, with a timeout to flush partial batches
            result = await asyncio.wait_for(results_queue.get(), timeout=2.0)
            
            try:
                # Parse JSON
                parsed = json.loads(result["content"])
                validated = GraphExtraction.model_validate(parsed)
                
                # Aggregate
                for e in validated.entities:
                    batch_entities.append({
                        "name": e.name, "type": e.type, "description": e.description, "source_url": result["source_url"]
                    })
                for r in validated.relationships:
                    batch_relationships.append({
                        "source": r.source, "target": r.target, "type": r.type,
                        "exact_quote": r.exact_quote, "source_url": result["source_url"]
                    })
            except Exception as e:
                print(f"Error parsing/validating JSON for chunk {result['doc_id']}: {e}")
                
            processed += 1
            results_queue.task_done()
            
        except asyncio.TimeoutError:
            # Timeout reached, flush if we have anything
            pass
            
        # Write if batch is full or it's been > 5 seconds since last write, or we're done
        current_time = time.time()
        should_write = (
            len(batch_entities) + len(batch_relationships) >= batch_size or
            (current_time - last_write_time > 5.0 and (batch_entities or batch_relationships)) or
            (processed == total_chunks and (batch_entities or batch_relationships))
        )
        
        if should_write:
            try:
                async with driver.session() as neo4j_session:
                    if batch_entities:
                        await neo4j_session.run(
                            """
                            UNWIND $entities AS entity
                            MERGE (e:RawEntity {name: entity.name, pipeline_id: $pipeline_id})
                            SET e.type = entity.type, e.description = entity.description, e.source_url = entity.source_url
                            """,
                            entities=batch_entities,
                            pipeline_id=site_id
                        )
                    if batch_relationships:
                        await neo4j_session.run(
                            """
                            UNWIND $relationships AS rel
                            MERGE (s:RawEntity {name: rel.source, pipeline_id: $pipeline_id})
                            MERGE (t:RawEntity {name: rel.target, pipeline_id: $pipeline_id})
                            MERGE (s)-[r:RAW_RELATIONSHIP {type: rel.type, pipeline_id: $pipeline_id}]->(t)
                            SET r.exact_quote = rel.exact_quote, r.source_url = rel.source_url
                            """,
                            relationships=batch_relationships,
                            pipeline_id=site_id
                        )
                print(f"Flushed batch to Neo4j: {len(batch_entities)} entities, {len(batch_relationships)} relationships")
            except Exception as e:
                print(f"Error writing batch to Neo4j: {e}")
                
            # Clear batches
            batch_entities = []
            batch_relationships = []
            last_write_time = time.time()
            
            # Publish progress
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": processed,
                "total_chunks": total_chunks,
                "current_phase": "Phase 1: Raw Extraction",
                "message": f"Processed {processed}/{total_chunks} chunks."
            })


async def process_resolution_batch_with_sem(batch: List[Any], site_id: str, resolution_chain: Any, sem: asyncio.Semaphore, cancel_event: asyncio.Event, progress_state: dict):
    if cancel_event.is_set():
        return
        
    async with sem:
        if cancel_event.is_set():
            return
            
        try:
            # 120 second strict timeout for Gemini resolution
            res_result = await asyncio.wait_for(resolution_chain.ainvoke({"entities": str(batch)}), timeout=120.0)
            
            async with driver.session() as neo4j_session:
                for canonical in res_result.canonical_entities:
                    await neo4j_session.run(
                        """
                        MERGE (c:CanonicalEntity {name: $canonical_name, pipeline_id: $pipeline_id})
                        SET c.type = $type
                        """,
                        canonical_name=canonical.canonical_name,
                        type=canonical.type,
                        pipeline_id=site_id
                    )
                    
                    for raw_name in canonical.raw_names:
                        await neo4j_session.run(
                            """
                            MATCH (r:RawEntity {name: $raw_name, pipeline_id: $pipeline_id})
                            MATCH (c:CanonicalEntity {name: $canonical_name, pipeline_id: $pipeline_id})
                            MERGE (r)-[:RESOLVES_TO]->(c)
                            """,
                            raw_name=raw_name,
                            canonical_name=canonical.canonical_name,
                            pipeline_id=site_id
                        )
        except asyncio.TimeoutError:
            print("Timeout in canonical resolution batch")
        except Exception as e:
            print(f"Error in canonical resolution batch: {e}")
            
        progress_state["processed_entities"] += len(batch)
        processed = progress_state["processed_entities"]
        total = progress_state["total_entities"]
        
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": progress_state["total_chunks"],
            "total_chunks": progress_state["total_chunks"],
            "current_phase": "Phase 2: Canonical Resolution",
            "message": f"Resolved batch {processed}/{total} entities."
        })


async def run_graph_generation_worker(site_id: str, niche: str, cancel_event: asyncio.Event):
    try:
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": 0,
            "current_phase": "Initialization",
            "message": "Starting graph generation worker..."
        })

        # 1. Fetch all chunks for the site
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(DataSource.id).where(DataSource.site_id == site_id))
            data_source_ids = result.scalars().all()
            
            if not data_source_ids:
                await event_manager.publish(site_id, {
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
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": 0,
                "total_chunks": 0,
                "current_phase": "Error",
                "message": "No chunks found to process."
            })
            return

        # Stage 1: Semantic Funnel (Filtering)
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": total_raw_chunks,
            "current_phase": "Stage 1: Semantic Funnel",
            "message": f"Generating anchor vectors for niche: {niche}..."
        })
        
        anchors = await generate_anchor_vectors(niche)
        
        await event_manager.publish(site_id, {
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
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": 0,
                "total_chunks": total_raw_chunks,
                "current_phase": "Error",
                "message": "Semantic Funnel filtered out all chunks. No data left to process."
            })
            return

        # Phase 1: Raw Extraction (Using Local vLLM Engine)
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": total_chunks,
            "current_phase": "Phase 1: Raw Extraction",
            "message": f"Semantic Funnel kept {total_chunks}/{total_raw_chunks} chunks. Starting OpenIE extraction..."
        })

        # Set up queues for producer-consumer architecture
        task_queue = asyncio.Queue()
        results_queue = asyncio.Queue()
        
        # Populate the task queue with filtered documents
        for doc in filtered_documents:
            task_queue.put_nowait((doc, site_id))
            
        connector = aiohttp.TCPConnector(limit=200)
        async with aiohttp.ClientSession(connector=connector) as http_session:
            # Start the consumer task
            consumer_task = asyncio.create_task(
                neo4j_batch_consumer(results_queue, total_chunks, site_id, cancel_event)
            )
            
            # Start the producer tasks (e.g., 200 concurrent workers)
            num_workers = 200
            producers = [
                asyncio.create_task(llm_producer_worker(i, task_queue, results_queue, http_session, cancel_event))
                for i in range(num_workers)
            ]
            
            # Wait for all tasks in the queue to be processed
            await task_queue.join()
            
            # Wait for all results to be consumed
            await results_queue.join()
            
            # Cancel the consumer task if it's still waiting on the queue
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        if cancel_event.is_set():
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": progress_state["processed"],
                "total_chunks": total_chunks,
                "current_phase": "Cancelled",
                "message": "Graph generation cancelled by user during Phase 1."
            })
            return

        # Phase 2: Canonical Resolution (Using Vector Embeddings + DBSCAN)
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 2: Canonical Resolution",
            "message": "Fetching raw entities for clustering..."
        })

        async with driver.session() as neo4j_session:
            result = await neo4j_session.run(
                "MATCH (e:RawEntity {pipeline_id: $pipeline_id}) RETURN e.name as name, e.type as type, e.description as description",
                pipeline_id=site_id
            )
            records = await result.data()
            raw_entities = [{"name": r["name"], "type": r["type"], "description": r.get("description", "")} for r in records]

        if not raw_entities:
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Complete",
                "message": "No entities extracted. Graph generation complete."
            })
            return

        await event_manager.publish(site_id, {
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
        # eps=0.15 is a good starting point for all-MiniLM-L6-v2 cosine distance (using metric='cosine')
        clustering = DBSCAN(eps=0.15, min_samples=1, metric='cosine').fit(embeddings)
        labels = clustering.labels_

        # Group entities by cluster
        clusters = {}
        for i, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(raw_entities[i])

        # Write to Neo4j
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 2: Canonical Resolution",
            "message": f"Writing {len(clusters)} canonical entities to database..."
        })

        async with driver.session() as neo4j_session:
            for label, cluster_entities in clusters.items():
                if cancel_event.is_set():
                    break
                    
                # The canonical name is the most common name in the cluster, or the shortest
                canonical_name = sorted(cluster_entities, key=lambda x: len(x["name"]))[0]["name"]
                # Use the most common type
                types = [e["type"] for e in cluster_entities if e["type"]]
                canonical_type = max(set(types), key=types.count) if types else "Unknown"

                # Use the longest description
                descriptions = [e["description"] for e in cluster_entities if e.get("description")]
                canonical_description = max(descriptions, key=len) if descriptions else ""

                await neo4j_session.run(
                    """
                    MERGE (c:CanonicalEntity {name: $canonical_name, pipeline_id: $pipeline_id})
                    SET c.type = $type, c.description = $description
                    """,
                    canonical_name=canonical_name,
                    type=canonical_type,
                    description=canonical_description,
                    pipeline_id=site_id
                )
                
                # Link raw entities to canonical
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

        if cancel_event.is_set():
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Cancelled",
                "message": "Graph generation cancelled by user during Phase 2."
            })
            return

        # Phase 3: GraphRAG Community Detection
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 3: Community Detection",
            "message": "Running Louvain community detection..."
        })

        async with driver.session() as neo4j_session:
            # 1. Project the graph into GDS memory
            graph_name = f"graph_{site_id.replace('-', '_')}"
            
            # Drop existing graph if it exists
            await neo4j_session.run(f"CALL gds.graph.drop('{graph_name}', false)")
            
            # Create the projection
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
            
            # 2. Run Louvain and write community IDs back to the nodes
            await neo4j_session.run(
                f"""
                CALL gds.louvain.write('{graph_name}', {{ writeProperty: 'community_id' }})
                """
            )
            
            # 3. Fetch communities and their top entities to generate summaries
            await event_manager.publish(site_id, {
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
            
            # Drop the in-memory graph
            await neo4j_session.run(f"CALL gds.graph.drop('{graph_name}', false)")

            # Generate summaries for each community
            for comm in communities:
                if cancel_event.is_set():
                    break
                    
                community_id = comm["community_id"]
                entities = comm["entities"]
                
                # Skip tiny communities (noise)
                if len(entities) < 3:
                    continue
                    
                # Ask Gemini to summarize the community
                prompt = f"You are a market analyst. Look at this list of entities that form a distinct cluster in a market graph. Provide a short, 3-5 word descriptive name for this sector, and a 1-2 sentence summary of what this sector represents.\n\nEntities: {', '.join(entities[:50])}" # Limit to top 50 entities for context size
                
                try:
                    summary_result = await llm.ainvoke(prompt)
                    # Simple parsing (assuming Gemini returns a name on line 1 and summary on line 2, but we'll just store the whole response for now)
                    summary_text = summary_result.content
                    
                    # Create the Community Meta-Node
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
                        name=f"Sector {community_id}" # Fallback name, can be refined by parsing Gemini's output better
                    )
                except Exception as e:
                    print(f"Error generating summary for community {community_id}: {e}")

        if cancel_event.is_set():
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Cancelled",
                "message": "Graph generation cancelled by user during Phase 3."
            })
            return

        # Phase 4: Graph Pruning (Slop Removal)
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 4: Graph Pruning",
            "message": "Identifying and removing generic 'slop' nodes..."
        })

        async with driver.session() as neo4j_session:
            # Identify supernodes (degree > 50)
            result = await neo4j_session.run(
                """
                MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
                OPTIONAL MATCH (c)-[r]-()
                WITH c, count(r) as degree
                WHERE degree > 50
                RETURN id(c) as id, c.name as name, c.type as type, c.description as description, degree
                ORDER BY degree DESC
                """,
                pipeline_id=site_id
            )
            supernodes = await result.data()

            if supernodes:
                print(f"Found {len(supernodes)} potential slop nodes. Verifying with LLM...")
                nodes_to_delete = []
                
                for node in supernodes:
                    if cancel_event.is_set():
                        break
                        
                    prompt = f"""You are a data quality filter for a market intelligence knowledge graph.
I will give you the name, type, and description of a highly-connected node in the graph.
Your job is to determine if this node is a generic document term/slop (e.g., 'Section 6', 'Page 4', 'Introduction', 'Table of Contents', 'Figure 1') OR a real-world entity (e.g., a company, person, technology, regulation, location).

Node Name: {node['name']}
Node Type: {node['type']}
Node Description: {node['description']}

Respond with exactly one word: "SLOP" if it is a generic document term, or "VALID" if it is a real-world entity."""
                    
                    try:
                        verification_result = await llm.ainvoke(prompt)
                        response_text = verification_result.content.strip().upper()
                        
                        if "SLOP" in response_text:
                            nodes_to_delete.append(node['id'])
                            print(f"Flagged as SLOP: {node['name']} (Degree: {node['degree']})")
                        else:
                            print(f"Validated: {node['name']} (Degree: {node['degree']})")
                    except Exception as e:
                        print(f"Error verifying node {node['name']}: {e}")

                if nodes_to_delete:
                    await event_manager.publish(site_id, {
                        "type": "graph_progress",
                        "processed_chunks": total_chunks,
                        "total_chunks": total_chunks,
                        "current_phase": "Phase 4: Graph Pruning",
                        "message": f"Removing {len(nodes_to_delete)} generic slop nodes..."
                    })
                    
                    # Delete the slop nodes
                    for node_id in nodes_to_delete:
                        await neo4j_session.run(
                            """
                            MATCH (n) WHERE id(n) = $node_id
                            DETACH DELETE n
                            """,
                            node_id=node_id
                        )
                    print(f"Successfully deleted {len(nodes_to_delete)} slop nodes.")

        if cancel_event.is_set():
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Cancelled",
                "message": "Graph generation cancelled by user during Phase 4."
            })
            return

        # Phase 5: Document Nodes & MENTIONS
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 5: Document Nodes",
            "message": "Creating Document nodes and MENTIONS edges..."
        })

        try:
            async with driver.session() as neo4j_session:
                for doc in filtered_documents:
                    if cancel_event.is_set():
                        break
                    
                    source_url = None
                    if isinstance(doc.metadata_json, dict):
                        source_url = doc.metadata_json.get("source_url")
                    
                    if not source_url:
                        continue

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

                    # Create Document node
                    await neo4j_session.run(
                        """
                        MERGE (d:Document {url: $url, pipeline_id: $pipeline_id})
                        SET d.id = $doc_id, d.title = $title, d.type = $type
                        """,
                        url=source_url,
                        pipeline_id=site_id,
                        doc_id=str(doc.id),
                        title=doc.title or source_url,
                        type=doc_type
                    )

                    # Create MENTIONS edges
                    await neo4j_session.run(
                        """
                        MATCH (d:Document {url: $url, pipeline_id: $pipeline_id})
                        MATCH (r:RawEntity {source_url: $url, pipeline_id: $pipeline_id})-[:RESOLVES_TO]->(c:CanonicalEntity {pipeline_id: $pipeline_id})
                        MERGE (d)-[:MENTIONS]->(c)
                        """,
                        url=source_url,
                        pipeline_id=site_id
                    )
                    
                    await neo4j_session.run(
                        """
                        MATCH (d:Document {url: $url, pipeline_id: $pipeline_id})
                        MATCH (s:RawEntity)-[rel:RAW_RELATIONSHIP {source_url: $url, pipeline_id: $pipeline_id}]->(t:RawEntity)
                        MATCH (s)-[:RESOLVES_TO]->(cs:CanonicalEntity)
                        MATCH (t)-[:RESOLVES_TO]->(ct:CanonicalEntity)
                        MERGE (d)-[:MENTIONS]->(cs)
                        MERGE (d)-[:MENTIONS]->(ct)
                        """,
                        url=source_url,
                        pipeline_id=site_id
                    )
        except Exception as e:
            print(f"Error in Phase 5: {e}")

        if cancel_event.is_set():
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Cancelled",
                "message": "Graph generation cancelled by user during Phase 5."
            })
            return

        # Phase 6: Semantic Edges
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Phase 6: Semantic Edges",
            "message": "Generating vector similarity edges..."
        })

        try:
            # Document-to-Document Similarity (Chunk-Level pgvector)
            url_embeddings = {}
            for doc in filtered_documents:
                if not doc.embedding or not isinstance(doc.metadata_json, dict):
                    continue
                source_url = doc.metadata_json.get("source_url")
                if not source_url:
                    continue
                
                if source_url not in url_embeddings:
                    url_embeddings[source_url] = []
                url_embeddings[source_url].append(np.array(doc.embedding))
                
            urls = list(url_embeddings.keys())
            if len(urls) >= 2:
                threshold = 0.85
                edges = []
                for i in range(len(urls)):
                    url_a = urls[i]
                    chunks_a = np.array(url_embeddings[url_a])
                    
                    for j in range(i + 1, len(urls)):
                        url_b = urls[j]
                        chunks_b = np.array(url_embeddings[url_b])
                        
                        sim_matrix = cosine_similarity(chunks_a, chunks_b)
                        max_sim = float(np.max(sim_matrix))
                        
                        if max_sim > threshold:
                            edges.append({
                                "source": url_a,
                                "target": url_b,
                                "weight": max_sim
                            })
                            
                if edges:
                    async with driver.session() as neo4j_session:
                        batch_size = 1000
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
                                pipeline_id=site_id
                            )
        except Exception as e:
            print(f"Error in Phase 6: {e}")

        if cancel_event.is_set():
            await event_manager.publish(site_id, {
                "type": "graph_progress",
                "processed_chunks": total_chunks,
                "total_chunks": total_chunks,
                "current_phase": "Cancelled",
                "message": "Graph generation cancelled by user during Phase 6."
            })
            return

        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": total_chunks,
            "total_chunks": total_chunks,
            "current_phase": "Complete",
            "message": "Graph generation completed successfully!"
        })

    except Exception as e:
        print(f"Graph generation failed: {e}")
        await event_manager.publish(site_id, {
            "type": "graph_progress",
            "processed_chunks": 0,
            "total_chunks": 0,
            "current_phase": "Error",
            "message": f"Graph generation failed: {str(e)}"
        })
