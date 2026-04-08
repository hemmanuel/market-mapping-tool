from typing import List, Dict, Any
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel, Field

from src.agents.state import AgentState, SearchQuery, ExtractedEntity, ExtractedRelationship
from src.db.neo4j_session import driver
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

def planner_node(state: AgentState) -> AgentState:
    """Generates search queries based on the niche and schema."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Sourcing Strategist. Generate highly targeted search queries to find information about the given niche and schema. Target specific domains like prnewswire.com, techcrunch.com, etc."),
        ("user", "Niche: {niche}\nEntities: {schema_entities}\nRelationships: {schema_relationships}")
    ])
    
    chain = prompt | llm.with_structured_output(PlannerOutput)
    result = chain.invoke({
        "niche": state["niche"],
        "schema_entities": state["schema_entities"],
        "schema_relationships": state["schema_relationships"]
    })
    
    return {**state, "search_queries": result.queries}

def search_node(state: AgentState) -> AgentState:
    """Executes searches to find URLs. Mocking for now, but could use Tavily."""
    # In a real implementation, use Tavily or Serper here.
    # For this prototype, we'll generate some dummy URLs based on the queries.
    urls = []
    for query in state.get("search_queries", []):
        domain = query["target_domains"][0] if query["target_domains"] else "example.com"
        urls.append(f"https://{domain}/news/article-about-{state['niche'].replace(' ', '-').lower()}")
    
    return {**state, "urls_to_scrape": urls}

def scrape_node(state: AgentState) -> AgentState:
    """Downloads text from a URL."""
    urls = state.get("urls_to_scrape", [])
    if not urls:
        return {**state, "current_url": None, "raw_text": None}
    
    # Pop the first URL to process
    current_url = urls.pop(0)
    
    # Mock scraping for now to avoid actual network calls in the agent loop if not needed,
    # but let's try a real request if it's a real URL, else mock.
    raw_text = f"This is a mock article about {state['niche']} from {current_url}. It mentions several companies and investors."
    
    try:
        if "example.com" not in current_url:
            response = httpx.get(current_url, timeout=10.0)
            soup = BeautifulSoup(response.text, 'html.parser')
            raw_text = soup.get_text(separator=' ', strip=True)[:5000] # Limit text
    except Exception as e:
        print(f"Failed to scrape {current_url}: {e}")
    
    return {**state, "urls_to_scrape": urls, "current_url": current_url, "raw_text": raw_text}

def bouncer_node(state: AgentState) -> AgentState:
    """Scores relevance of the text."""
    if not state.get("raw_text"):
        return {**state, "is_relevant": False, "relevance_reason": "No text to evaluate"}
        
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Relevance Bouncer. Determine if the text is relevant to the niche: {niche}."),
        ("user", "Text: {raw_text}")
    ])
    
    chain = prompt | llm.with_structured_output(BouncerOutput)
    result = chain.invoke({
        "niche": state["niche"],
        "raw_text": state["raw_text"][:2000] # Evaluate first 2000 chars
    })
    
    return {**state, "is_relevant": result.is_relevant, "relevance_reason": result.reason}

def extractor_node(state: AgentState) -> AgentState:
    """Extracts strict JSON matching the schema."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a strict data extraction parser. Extract entities and relationships from the provided text using the provided schema. You may ONLY extract information explicitly stated in the text. Do NOT use outside knowledge. Provide exact quotes and source URLs."),
        ("user", "Schema Entities: {schema_entities}\nSchema Relationships: {schema_relationships}\nSource URL: {current_url}\nText: {raw_text}")
    ])
    
    chain = prompt | llm.with_structured_output(ExtractionOutput)
    result = chain.invoke({
        "schema_entities": state["schema_entities"],
        "schema_relationships": state["schema_relationships"],
        "current_url": state["current_url"],
        "raw_text": state["raw_text"]
    })
    
    return {
        **state, 
        "extracted_entities": result.entities, 
        "extracted_relationships": result.relationships
    }

def validator_node(state: AgentState) -> AgentState:
    """Checks JSON against raw text for hallucinations."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Fact-Checking Validator. Verify the extracted entities and relationships against the original text. Ensure exact quotes match the text and no outside knowledge was used."),
        ("user", "Original Text: {raw_text}\nExtracted Entities: {extracted_entities}\nExtracted Relationships: {extracted_relationships}")
    ])
    
    chain = prompt | llm.with_structured_output(ValidatorOutput)
    result = chain.invoke({
        "raw_text": state["raw_text"],
        "extracted_entities": state["extracted_entities"],
        "extracted_relationships": state["extracted_relationships"]
    })
    
    return {
        **state, 
        "is_valid": result.is_accurate, 
        "validation_errors": result.errors_found
    }

async def storage_node(state: AgentState) -> AgentState:
    """Writes validated data to Neo4j."""
    if not state.get("is_valid") or not state.get("extracted_entities"):
        return state
        
    pipeline_id = state["pipeline_id"]
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
                print(f"Failed to store relationship {rel}: {e}")
                
    return {
        **state,
        "stored_entities": state.get("stored_entities", 0) + stored_entities,
        "stored_relationships": state.get("stored_relationships", 0) + stored_relationships
    }
