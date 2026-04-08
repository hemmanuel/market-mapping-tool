from typing import List, Dict, Any
import os
import time
import tempfile
import pandas as pd
from pypdf import PdfReader
from docx import Document
from pptx import Presentation
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel, Field

from src.agents.state import AgentState, SearchQuery
from src.db.neo4j_session import driver
from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.models.relational import DataSource, Document as PGDocument
from sqlalchemy.future import select
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

# Initialize LLM and Embeddings
llm = ChatGoogleGenerativeAI(model="gemini-3.1-pro-preview", api_key=os.getenv("GEMINI_API_KEY"))
embeddings = GoogleGenerativeAIEmbeddings(model="text-embedding-004", google_api_key=os.getenv("GEMINI_API_KEY"))

# Models for structured output
class PlannerOutput(BaseModel):
    queries: List[SearchQuery] = Field(description="List of search queries and target domains")

class BouncerOutput(BaseModel):
    is_relevant: bool = Field(description="Whether the text is relevant to the niche")
    reason: str = Field(description="Reason for relevance or irrelevance")

async def planner_node(state: AgentState) -> AgentState:
    """Generates search queries based on the niche and schema."""
    pipeline_id = state["pipeline_id"]
    await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Planner] Analyzing niche: {state['niche']}"})
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Sourcing Strategist. Generate highly targeted search queries to find information about the given niche and schema. Target specific domains like prnewswire.com, techcrunch.com, etc. Occasionally append filetype operators (e.g., filetype:pdf, filetype:pptx, filetype:xlsx) to actively hunt for industry reports, presentations, and datasets."),
        ("user", "Niche: {niche}\nEntities: {schema_entities}\nRelationships: {schema_relationships}")
    ])
    
    chain = prompt | llm.with_structured_output(PlannerOutput)
    result = await chain.ainvoke({
        "niche": state["niche"],
        "schema_entities": state["schema_entities"],
        "schema_relationships": state["schema_relationships"]
    })
    
    for q in result.queries:
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Planner] Generated query: '{q['query']}'"})
    
    return {**state, "search_queries": result.queries}

async def search_node(state: AgentState) -> AgentState:
    """Executes searches to find URLs using Serper.dev."""
    pipeline_id = state["pipeline_id"]
    urls = []
    
    serper_api_key = os.getenv("SERPER_API_KEY")
    if not serper_api_key:
        await event_manager.publish(pipeline_id, {"type": "log", "message": "[Searcher] Error: SERPER_API_KEY is not set."})
        return {**state, "urls_to_scrape": urls}
    
    for query in state.get("search_queries", []):
        search_term = query["query"]
        if query.get("target_domains"):
            domain_str = " OR ".join([f"site:{d}" for d in query["target_domains"]])
            search_term = f"{search_term} ({domain_str})"
            
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Searcher] Executing search for: '{search_term}'"})
        
        try:
            headers = {
                'X-API-KEY': serper_api_key,
                'Content-Type': 'application/json'
            }
            payload = {
                "q": search_term,
                "num": 10
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post('https://google.serper.dev/search', headers=headers, json=payload, timeout=10.0)
                response.raise_for_status()
                
                data = response.json()
                organic_results = data.get("organic", [])
                
                found_urls = 0
                for r in organic_results:
                    if "link" in r:
                        urls.append(r["link"])
                        found_urls += 1
                        
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Searcher] Found {found_urls} URLs for query."})
                
        except Exception as e:
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Searcher] Search failed for '{search_term}': {e}"})
            print(f"Serper search failed for '{search_term}': {e}")
            
    # Deduplicate URLs while preserving order
    unique_urls = []
    for url in urls:
        if url not in unique_urls:
            unique_urls.append(url)
            
    await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Searcher] Total unique URLs queued: {len(unique_urls)}"})
    return {**state, "urls_to_scrape": unique_urls}

async def scrape_node(state: AgentState) -> AgentState:
    """Downloads text from a URL, handling multiple formats."""
    pipeline_id = state["pipeline_id"]
    urls = state.get("urls_to_scrape", [])
    if not urls:
        return {**state, "current_url": None, "raw_text": None}
    
    # Pop the first URL to process
    current_url = urls.pop(0)
    raw_text = ""
    
    await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Attempting to download: {current_url}"})
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(current_url, headers=headers, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
            
            content_type = response.headers.get("Content-Type", "").lower()
            
            if "application/pdf" in content_type or current_url.lower().endswith(".pdf"):
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Detected PDF document. Extracting text..."})
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(response.content)
                    tmp_path = tmp.name
                try:
                    reader = PdfReader(tmp_path)
                    text_parts = [page.extract_text() for page in reader.pages if page.extract_text()]
                    raw_text = " ".join(text_parts)
                finally:
                    os.unlink(tmp_path)
                    
            elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type or current_url.lower().endswith(".docx"):
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Detected Word document. Extracting text..."})
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                    tmp.write(response.content)
                    tmp_path = tmp.name
                try:
                    doc = Document(tmp_path)
                    raw_text = " ".join([p.text for p in doc.paragraphs])
                finally:
                    os.unlink(tmp_path)
                    
            elif "application/vnd.openxmlformats-officedocument.presentationml.presentation" in content_type or current_url.lower().endswith(".pptx"):
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Detected PowerPoint document. Extracting text..."})
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as tmp:
                    tmp.write(response.content)
                    tmp_path = tmp.name
                try:
                    prs = Presentation(tmp_path)
                    text_parts = []
                    for slide in prs.slides:
                        for shape in slide.shapes:
                            if hasattr(shape, "text"):
                                text_parts.append(shape.text)
                    raw_text = " ".join(text_parts)
                finally:
                    os.unlink(tmp_path)
                    
            elif "spreadsheet" in content_type or "excel" in content_type or current_url.lower().endswith(".xlsx") or current_url.lower().endswith(".csv"):
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Detected Spreadsheet. Extracting data..."})
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(response.content)
                    tmp_path = tmp.name
                try:
                    if current_url.lower().endswith(".csv") or "csv" in content_type:
                        df = pd.read_csv(tmp_path)
                    else:
                        df = pd.read_excel(tmp_path)
                    raw_text = df.to_string()
                finally:
                    os.unlink(tmp_path)
                    
            else:
                # Default to HTML
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Detected HTML page. Parsing..."})
                soup = BeautifulSoup(response.text, 'html.parser')
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                raw_text = soup.get_text(separator=' ', strip=True)
                
            # Truncate to ~15000 chars
            raw_text = raw_text[:15000]
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Successfully extracted {len(raw_text)} characters."})
            
    except Exception as e:
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Scraper] Failed to download/parse: {e}"})
        print(f"Failed to scrape {current_url}: {e}")
        raw_text = "" # Return empty text so bouncer rejects it
    
    return {**state, "urls_to_scrape": urls, "current_url": current_url, "raw_text": raw_text}

async def bouncer_node(state: AgentState) -> AgentState:
    """Scores relevance of the text."""
    pipeline_id = state["pipeline_id"]
    await event_manager.publish(pipeline_id, {"type": "log", "message": "[Bouncer] Evaluating text relevance..."})
    
    if not state.get("raw_text"):
        await event_manager.publish(pipeline_id, {"type": "log", "message": "[Bouncer] Rejected: No text to evaluate"})
        return {**state, "is_relevant": False, "relevance_reason": "No text to evaluate"}
        
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Relevance Bouncer. Determine if the text is relevant to the niche: {niche}."),
        ("user", "Text: {raw_text}")
    ])
    
    chain = prompt | llm.with_structured_output(BouncerOutput)
    result = await chain.ainvoke({
        "niche": state["niche"],
        "raw_text": state["raw_text"][:2000] # Evaluate first 2000 chars
    })
    
    if result.is_relevant:
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Bouncer] Approved: {result.reason}"})
    else:
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Bouncer] Rejected: {result.reason}"})
        
    return {**state, "is_relevant": result.is_relevant, "relevance_reason": result.reason}

async def vector_storage_node(state: AgentState) -> AgentState:
    """Chunks text, generates embeddings, and saves to PostgreSQL."""
    pipeline_id = state["pipeline_id"]
    await event_manager.publish(pipeline_id, {"type": "log", "message": "[VectorStorage] Preparing to save chunks to PostgreSQL..."})
    
    if not state.get("raw_text"):
        await event_manager.publish(pipeline_id, {"type": "log", "message": "[VectorStorage] Skipped: No raw text to process."})
        return state
        
    raw_text = state["raw_text"]
    current_url = state["current_url"]
    
    # Chunk the text
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_text(raw_text)
    await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Split text into {len(chunks)} chunks."})
    
    if not chunks:
        return state
        
    # Generate embeddings
    try:
        chunk_embeddings = await embeddings.aembed_documents(chunks)
    except Exception as e:
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Failed to generate embeddings: {e}"})
        print(f"Failed to embed chunks: {e}")
        return state
        
    stored_chunks = 0
    
    async with AsyncSessionLocal() as session:
        try:
            # Find a data source for this pipeline (site)
            # This assumes at least one data source exists for the site
            result = await session.execute(select(DataSource).where(DataSource.site_id == pipeline_id).limit(1))
            data_source = result.scalars().first()
            
            if not data_source:
                await event_manager.publish(pipeline_id, {"type": "log", "message": "[VectorStorage] Error: No DataSource found for this pipeline."})
                return state
                
            for i, chunk in enumerate(chunks):
                doc = PGDocument(
                    data_source_id=data_source.id,
                    title=f"Extracted from {current_url} (Chunk {i+1})",
                    raw_text=chunk,
                    embedding=chunk_embeddings[i],
                    metadata_json={"source_url": current_url, "chunk_index": i}
                )
                session.add(doc)
                stored_chunks += 1
                
            await session.commit()
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Saved {stored_chunks} embedded chunks to PostgreSQL."})
            
        except Exception as e:
            await session.rollback()
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Database error: {e}"})
            print(f"Database error in VectorStorage: {e}")
            
    return {
        **state,
        "stored_chunks": state.get("stored_chunks", 0) + stored_chunks
    }
