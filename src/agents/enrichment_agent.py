import asyncio
import os
import json
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from src.agents.schemas.enrichment import CompanyEnrichment

load_dotenv()

# Initialize Gemini 3 Flash
llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"), 
    api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.0
)

async def _serper_search(query: str, num: int = 5, max_retries: int = 5) -> List[Dict[str, Any]]:
    """Helper to perform a Google Search via Serper.dev with exponential backoff."""
    serper_api_key = os.getenv("SERPER_API_KEY")
    if not serper_api_key:
        print("Warning: SERPER_API_KEY not set.")
        return []
        
    headers = {
        'X-API-KEY': serper_api_key,
        'Content-Type': 'application/json'
    }
    payload = {"q": query, "num": num}
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post('https://google.serper.dev/search', headers=headers, json=payload, timeout=15.0)
                response.raise_for_status()
                data = response.json()
                return data.get("organic", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait_time = 2 ** attempt
                print(f"Serper 429 Too Many Requests for '{query}'. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(wait_time)
            else:
                print(f"Serper HTTP error for '{query}': {e}. Skipping.")
                break
        except Exception as e:
            wait_time = 2 ** attempt
            print(f"Serper connection error for '{query}': {e}. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            
    print(f"Exhausted all {max_retries} retries for Serper search: '{query}'. Skipping and documenting failure.")
    return []

async def _scrape_url(url: str, max_retries: int = 3) -> str:
    """Helper to scrape text from a URL using Jina Reader API with exponential backoff."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"https://r.jina.ai/{url}", headers=headers, timeout=20.0, follow_redirects=True)
                response.raise_for_status()
                text = response.text
                # Truncate to avoid massive token usage on single pages
                return text[:15000]
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [429, 500, 502, 503, 504]:
                wait_time = 2 ** attempt
                print(f"Scrape HTTP {e.response.status_code} for {url}. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(wait_time)
            else:
                print(f"Failed to scrape {url} (HTTP {e.response.status_code}). Skipping.")
                break
        except Exception as e:
            wait_time = 2 ** attempt
            print(f"Scrape connection error for {url}: {e}. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            
    print(f"Exhausted all {max_retries} retries for scraping: {url}. Skipping and documenting failure.")
    return ""

async def enrich_company(company_name: str, niche: str = "Technology") -> Optional[CompanyEnrichment]:
    """
    Executes a multi-step search strategy to build a comprehensive VC dossier for a company.
    """
    print(f"\n--- Starting Enrichment for: {company_name} ---")
    
    gathered_text = f"COMPANY NAME: {company_name}\nINDUSTRY/NICHE: {niche}\n\n"
    source_urls = []
    
    # Step 1: Primary Asset Search (Official Website)
    print("Step 1: Searching for official website...")
    primary_results = await _serper_search(f"{company_name} official website {niche}", num=3)
    if primary_results:
        top_url = primary_results[0].get("link")
        if top_url:
            print(f"-> Found likely official URL: {top_url}")
            source_urls.append(top_url)
            text = await _scrape_url(top_url)
            if text:
                gathered_text += f"--- SOURCE: OFFICIAL WEBSITE ({top_url}) ---\n{text}\n\n"

    # Step 2: Financial & Investor Search (Crunchbase/Pitchbook/News)
    print("Step 2: Searching for funding and investor data...")
    fin_query = f"{company_name} (site:crunchbase.com OR site:pitchbook.com OR \"raised\" OR \"funding\" OR \"series\")"
    fin_results = await _serper_search(fin_query, num=5)
    
    for res in fin_results[:3]:
        url = res.get("link")
        snippet = res.get("snippet", "")
        if url and url not in source_urls:
            print(f"-> Scraping financial source: {url}")
            source_urls.append(url)
            text = await _scrape_url(url)
            if text:
                gathered_text += f"--- SOURCE: FINANCIAL DATA ({url}) ---\nSnippet: {snippet}\n{text}\n\n"
            else:
                # If scraping fails (e.g., Crunchbase blocks it), at least keep the snippet
                gathered_text += f"--- SOURCE: FINANCIAL SNIPPET ({url}) ---\n{snippet}\n\n"

    # Step 3: Founder Deep-Dive (LinkedIn / Team pages)
    print("Step 3: Searching for founders and team...")
    team_query = f"{company_name} (\"founder\" OR \"CEO\") site:linkedin.com/in"
    team_results = await _serper_search(team_query, num=3)
    
    for res in team_results:
        url = res.get("link")
        snippet = res.get("snippet", "")
        if url and url not in source_urls:
            print(f"-> Found potential founder profile: {url}")
            source_urls.append(url)
            # LinkedIn blocks scraping heavily, so we rely mostly on the Serper snippet
            gathered_text += f"--- SOURCE: FOUNDER PROFILE ({url}) ---\nSnippet: {snippet}\n\n"

    # Step 4: Fallback/Exhaustion Loop for Missing Context
    print("Step 4: Executing general news/context fallback search...")
    news_query = f"{company_name} {niche} \"startup\" OR \"company\" overview"
    news_results = await _serper_search(news_query, num=3)
    
    for res in news_results:
        url = res.get("link")
        if url and url not in source_urls:
            print(f"-> Scraping fallback context: {url}")
            source_urls.append(url)
            text = await _scrape_url(url)
            if text:
                gathered_text += f"--- SOURCE: GENERAL CONTEXT ({url}) ---\n{text}\n\n"

    # Step 5: Synthesis via Gemini 3 Flash
    print(f"\nStep 5: Synthesizing {len(gathered_text)} characters of context via Gemini...")
    
    system_prompt = f"""You are an elite Venture Capital Analyst specializing in the {niche} sector.
I have scraped the web for information about a company named "{company_name}".

Your task is to synthesize this raw, messy data into a pristine, highly-structured VC Dossier.
You MUST output valid JSON matching the provided schema.

CRITICAL INSTRUCTIONS:
1. Be highly analytical and objective. Do not just copy marketing fluff.
2. If exact funding numbers (e.g., Total Raised, Latest Round) are missing, use "Undisclosed" or estimate based on context (e.g., "Seed (Est.)").
3. For the `dimension_scores` (0.0 to 1.0), use your deep industry knowledge to infer these scores based on their business model and tech stack.
4. For the `strategic_analysis` and `metric_rationales`, write insightful, multi-sentence paragraphs explaining your reasoning.
5. In `vc_dossier.source_urls`, include the URLs provided in the raw text.

If the company appears to be an incumbent, utility, or completely irrelevant noise (not a startup/tech company), you must still fill out the schema, but set `stage_estimate` to "Incumbent" or "Utility" and adjust the venture_scale_score to 0.0.
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "Raw Scraped Context:\n\n{context}")
    ])
    
    # Use structured output to force the exact Pydantic schema
    structured_llm = llm.with_structured_output(CompanyEnrichment)
    chain = prompt | structured_llm
    
    max_llm_retries = 5
    for attempt in range(max_llm_retries):
        try:
            result = await chain.ainvoke({"context": gathered_text})
            
            # Ensure source URLs are injected if the LLM missed them
            if not result.vc_dossier.source_urls:
                result.vc_dossier.source_urls = source_urls
                
            print(f"Successfully enriched: {result.company_name} (Stage: {result.stage_estimate})")
            return result
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = 2 ** attempt
                print(f"Gemini 429 Too Many Requests for {company_name}. Retrying in {wait_time}s (Attempt {attempt+1}/{max_llm_retries})...")
                await asyncio.sleep(wait_time)
            else:
                print(f"Failed to synthesize dossier for {company_name}: {e}. Skipping.")
                break
                
    print(f"Exhausted all {max_llm_retries} retries for Gemini synthesis on {company_name}. Skipping and documenting failure.")
    return None

if __name__ == "__main__":
    # Simple test execution
    async def test():
        company = "Fischer Block"
        niche = "Electric Power Grid Modernization"
        result = await enrich_company(company, niche)
        if result:
            print("\n--- FINAL JSON OUTPUT ---")
            print(result.model_dump_json(indent=2))
            
    asyncio.run(test())
