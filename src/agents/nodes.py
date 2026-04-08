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

from src.agents.state import AgentState, SearchQuery, ExtractedEntity, ExtractedRelationship
from src.db.neo4j_session import driver
from src.api.events import event_manager
from dotenv import load_dotenv

load_dotenv()

# Initialize LLM
llm = ChatGoogleGenerativeAI(model="gemini-3.1-pro-preview", api_key=os.getenv("GEMINI_API_KEY"))

# Models for structured output
class PlannerOutput(BaseModel):
    queries: List[SearchQuery] = Field(description="List of search queries and target domains")

class BouncerOutput(BaseModel):
    is_relevant: bool = Field(description="Whether the text is relevant to the niche")
    reason: str = Field(description="Reason for relevance or irrelevance")

class ExtractionOutput(BaseModel):
    entities: List[ExtractedEntity] = Field(description="List of extracted entities")
    relationships: List[ExtractedRelationship] = Field(description="List of extracted relationships")

class ValidatorOutput(BaseModel):
    is_accurate: bool = Field(description="Whether the extracted data is accurate based on the text")
    errors_found: List[str] = Field(description="List of errors found, empty if accurate")

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
                "num": 3
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

async def extractor_node(state: AgentState) -> AgentState:
    """Extracts strict JSON matching the schema."""
    pipeline_id = state["pipeline_id"]
    await event_manager.publish(pipeline_id, {"type": "log", "message": "[Extractor] Extracting entities and relationships..."})
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a strict data extraction parser. Extract entities and relationships from the provided text using the provided schema. You may ONLY extract information explicitly stated in the text. Do NOT use outside knowledge. Provide exact quotes and source URLs."),
        ("user", "Schema Entities: {schema_entities}\nSchema Relationships: {schema_relationships}\nSource URL: {current_url}\nText: {raw_text}")
    ])
    
    chain = prompt | llm.with_structured_output(ExtractionOutput)
    result = await chain.ainvoke({
        "schema_entities": state["schema_entities"],
        "schema_relationships": state["schema_relationships"],
        "current_url": state["current_url"],
        "raw_text": state["raw_text"]
    })
    
    await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Extractor] Found {len(result.entities)} entities and {len(result.relationships)} relationships."})
    
    return {
        **state, 
        "extracted_entities": result.entities, 
        "extracted_relationships": result.relationships
    }

async def validator_node(state: AgentState) -> AgentState:
    """Checks JSON against raw text for hallucinations."""
    pipeline_id = state["pipeline_id"]
    await event_manager.publish(pipeline_id, {"type": "log", "message": "[Validator] Checking for hallucinations..."})
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Fact-Checking Validator. Verify the extracted entities and relationships against the original text. Ensure exact quotes match the text and no outside knowledge was used."),
        ("user", "Original Text: {raw_text}\nExtracted Entities: {extracted_entities}\nExtracted Relationships: {extracted_relationships}")
    ])
    
    chain = prompt | llm.with_structured_output(ValidatorOutput)
    result = await chain.ainvoke({
        "raw_text": state["raw_text"],
        "extracted_entities": state["extracted_entities"],
        "extracted_relationships": state["extracted_relationships"]
    })
    
    if result.is_accurate:
        await event_manager.publish(pipeline_id, {"type": "log", "message": "[Validator] Data passed validation."})
    else:
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Validator] Failed: {result.errors_found}"})
        
    return {
        **state, 
        "is_valid": result.is_accurate, 
        "validation_errors": result.errors_found
    }

async def storage_node(state: AgentState) -> AgentState:
    """Writes validated data to Neo4j."""
    pipeline_id = state["pipeline_id"]
    await event_manager.publish(pipeline_id, {"type": "log", "message": "[Storage] Preparing to save to Neo4j..."})
    
    if not state.get("is_valid") or not state.get("extracted_entities"):
        await event_manager.publish(pipeline_id, {"type": "log", "message": "[Storage] Skipped: Data invalid or empty."})
        return state
        
    entities = state["extracted_entities"]
    relationships = state["extracted_relationships"]
    
    stored_entities = 0
    stored_relationships = 0
    
    async with driver.session() as session:
        for ent in entities:
            # Upsert entity
            query = f"""
            MERGE (e:`{ent['type']}` {{name: $name}})
            SET e.source_url = $source_url, e.exact_quote = $exact_quote, e.pipeline_id = $pipeline_id
            """
            await session.run(query, name=ent["name"], source_url=ent["source_url"], exact_quote=ent["exact_quote"], pipeline_id=pipeline_id)
            stored_entities += 1
            
        for rel in relationships:
            # Upsert relationship
            # Note: In a real system, we'd need to know the types of source and target to MATCH them properly.
            # For this prototype, we'll assume they exist and match by name across all labels.
            query = f"""
            MATCH (s {{name: $source}})
            MATCH (t {{name: $target}})
            MERGE (s)-[r:`{rel['type'].replace(' ', '_').upper()}`]->(t)
            SET r.source_url = $source_url, r.exact_quote = $exact_quote, r.pipeline_id = $pipeline_id
            """
            try:
                await session.run(query, source=rel["source"], target=rel["target"], source_url=rel["source_url"], exact_quote=rel["exact_quote"], pipeline_id=pipeline_id)
                stored_relationships += 1
            except Exception as e:
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Storage] Failed to store relationship: {e}"})
                print(f"Failed to store relationship {rel}: {e}")
                
    await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Storage] Saved {stored_entities} entities and {stored_relationships} relationships to Neo4j."})
    
    return {
        **state,
        "stored_entities": state.get("stored_entities", 0) + stored_entities,
        "stored_relationships": state.get("stored_relationships", 0) + stored_relationships
    }
