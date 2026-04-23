import os
import asyncio
from typing import List, Dict, Any
from sqlalchemy.future import select
from sqlalchemy import func
from src.db.session import AsyncSessionLocal
from src.db.neo4j_session import driver
from src.models.relational import Document as PGDocument, DataSource
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

async def generate_rag_insight(pipeline_id: str, target_id: int, target_type: str) -> str:
    """
    Generates a RAG-based insight for a given node in the graph.
    target_type should be either 'Entity' or 'Document'.
    """
    
    # 1. Graph Retrieval (Neo4j)
    graph_context = ""
    source_urls = set()
    query_text = ""
    
    async with driver.session() as neo4j_session:
        if target_type == 'Entity':
            # Fetch the CanonicalEntity and its 1-hop neighbors
            result = await neo4j_session.run(
                """
                MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
                WHERE id(c) = $target_id
                
                OPTIONAL MATCH (c)-[r:INTERACTS_WITH]-(n:CanonicalEntity {pipeline_id: $pipeline_id})
                
                RETURN 
                    c.name as central_name, c.description as central_description,
                    n.name as neighbor_name, n.type as neighbor_type,
                    r.type as rel_type, r.source_urls as source_urls,
                    CASE WHEN r IS NOT NULL THEN startNode(r) = c ELSE null END as is_outgoing
                """,
                pipeline_id=pipeline_id,
                target_id=target_id
            )
            records = await result.data()
            
            if not records or not records[0].get("central_name"):
                return "Entity not found in the knowledge graph."
                
            central_name = records[0]["central_name"]
            central_description = records[0]["central_description"] or ""
            query_text = f"{central_name} {central_description}"
            
            graph_context += f"Central Entity: {central_name}\n"
            graph_context += f"Description: {central_description}\n\n"
            graph_context += "Relationships:\n"
            
            for rec in records:
                if rec["neighbor_name"]:
                    direction = "->" if rec["is_outgoing"] else "<-"
                    graph_context += f"- {central_name} {direction} [{rec['rel_type']}] {direction} {rec['neighbor_name']} ({rec['neighbor_type']})\n"
                    
                    if rec["source_urls"]:
                        for url in rec["source_urls"]:
                            if url and url.strip():
                                source_urls.add(url.strip())
                                
        elif target_type == 'Document':
            # Fetch Document, its SIMILAR_TO neighbors, and MENTIONS entities
            result = await neo4j_session.run(
                """
                MATCH (d:Document {pipeline_id: $pipeline_id})
                WHERE id(d) = $target_id
                
                OPTIONAL MATCH (d)-[r_sim:SIMILAR_TO]-(sim_doc:Document {pipeline_id: $pipeline_id})
                OPTIONAL MATCH (d)-[r_mentions:MENTIONS]->(ent:CanonicalEntity {pipeline_id: $pipeline_id})
                
                RETURN 
                    d.title as doc_title, d.url as doc_url,
                    collect(DISTINCT {url: sim_doc.url, title: sim_doc.title, weight: r_sim.weight}) as similar_docs,
                    collect(DISTINCT {name: ent.name, type: ent.type}) as mentioned_entities
                """,
                pipeline_id=pipeline_id,
                target_id=target_id
            )
            records = await result.data()
            
            if not records or not records[0].get("doc_url"):
                return "Document not found in the knowledge graph."
                
            doc_title = records[0]["doc_title"]
            doc_url = records[0]["doc_url"]
            query_text = f"{doc_title}"
            source_urls.add(doc_url)
            
            graph_context += f"Central Document: {doc_title}\n"
            graph_context += f"URL: {doc_url}\n\n"
            
            similar_docs = [d for d in records[0]["similar_docs"] if d.get("url")]
            if similar_docs:
                graph_context += "Similar Documents:\n"
                for sim in similar_docs:
                    graph_context += f"- {sim['title']} (Similarity: {sim['weight']:.2f})\n"
                    source_urls.add(sim['url'])
                    
            mentioned_entities = [e for e in records[0]["mentioned_entities"] if e.get("name")]
            if mentioned_entities:
                graph_context += "\nMentioned Entities:\n"
                for ent in mentioned_entities:
                    graph_context += f"- {ent['name']} ({ent['type']})\n"
                    
        else:
            return "Invalid target_type. Must be 'Entity' or 'Document'."

    # 2. Text Retrieval (PostgreSQL + pgvector)
    if not source_urls:
        return "No source documents found to retrieve context from."
        
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001", 
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
    query_embedding = await embeddings.aembed_query(query_text)
    
    text_chunks = []
    async with AsyncSessionLocal() as session:
        # We want to find the top 10 most relevant chunks from the source_urls
        # using pgvector cosine distance
        result = await session.execute(
            select(
                PGDocument.raw_text, 
                PGDocument.metadata_json,
                PGDocument.embedding.cosine_distance(query_embedding).label("distance")
            )
            .join(DataSource, PGDocument.data_source_id == DataSource.id)
            .where(
                DataSource.site_id == pipeline_id,
                PGDocument.metadata_json['source_url'].astext.in_(list(source_urls)),
                PGDocument.embedding.is_not(None)
            )
            .order_by("distance")
            .limit(10)
        )
        
        for raw_text, metadata_json, distance in result:
            url = metadata_json.get("source_url", "Unknown URL")
            text_chunks.append({
                "text": raw_text,
                "url": url,
                "distance": distance
            })
            
    # 3. LLM Generation
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"), 
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.0
    )
    
    chunks_text = ""
    for i, chunk in enumerate(text_chunks):
        chunks_text += f"--- Chunk {i+1} [Source: {chunk['url']}] ---\n{chunk['text']}\n\n"
        
    prompt = f"""You are a VC/PE analyst. Analyze this central {target_type.lower()} and its network.
Provide a holistic description of this group, the dynamics at play, and why it is relevant from an investment perspective.

### Graph Context
{graph_context}

### Raw Text Evidence (Retrieved via RAG)
{chunks_text}

Provide a concise, insightful 2-3 paragraph analysis.
Whenever you mention a fact, relationship, or detail from the evidence, you MUST cite it using a Markdown link to the source URL provided in the Raw Text Evidence section.
Format citations like this: `[Source](URL)`. Do not use footnote numbers like [1].
If you cannot find evidence for a claim in the provided text chunks, do not state it.
"""

    print("--- PROMPT ---")
    print(prompt)
    print("--------------")
    
    max_retries = 3
    base_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            insight_result = await llm.ainvoke(prompt)
            content = insight_result.content
            
            if isinstance(content, list):
                content = "".join([
                    block.get("text", "") if isinstance(block, dict) else str(block) 
                    for block in content
                ])
                
            return str(content)
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"Hit API burst limit (429). Retrying in {delay} seconds (Attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
            
            print(f"Failed to generate RAG insight: {e}")
            return "Analysis could not be generated at this time due to an error."
            
    return "Analysis could not be generated at this time due to repeated API rate limits."