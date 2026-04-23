import asyncio
import os
import sys
from dotenv import load_dotenv
import httpx

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.session import AsyncSessionLocal
from src.models.relational import Site
from sqlalchemy.future import select
from src.agents.nodes import llm, MarketSizingOutput, CompanyExtractionOutput
from langchain_core.prompts import ChatPromptTemplate
from src.agents.enrichment_agent import enrich_company
from src.agents.neo4j_enrichment import save_enriched_company_to_neo4j

load_dotenv()

async def backfill_site(site: Site):
    print(f"Starting backfill for site: {site.name} (ID: {site.id})")
    
    # 1. Generate micro-buckets
    system_prompt = """You are a Market Sizing Expert. Your goal is to help exhaustively map a market niche by breaking it down into small, highly specific "micro-buckets".
    
    First, estimate the total number of active VC-backed startups and mature companies in the niche across all stages (Seed, Series A, Series B, Late, Public).
    Then, fracture the market into specific micro-buckets (by geography, sub-niche, or vintage) such that EACH bucket likely contains fewer than 50 companies.
    
    Example micro-buckets:
    - "Seed stage Electric Power startups in North America funded in 2023"
    - "Series A Grid Storage companies in Europe"
    - "Late-stage Virtual Power Plant companies"
    
    Return a comprehensive list of these micro-buckets."""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "Niche: {niche}")
    ])
    
    chain = prompt | llm.with_structured_output(MarketSizingOutput)
    try:
        result = await chain.ainvoke({"niche": site.name})
        micro_buckets = result.micro_buckets
        print(f"Generated {len(micro_buckets)} micro-buckets for {site.name}")
    except Exception as e:
        print(f"Failed to generate micro-buckets for {site.name}: {e}")
        return

    # 2. Active Serper search for early-stage companies
    serper_api_key = os.getenv("SERPER_API_KEY")
    if not serper_api_key:
        print("SERPER_API_KEY not set. Skipping active search.")
        return

    early_stage_companies = []
    
    async def search_bucket(bucket: str):
        bucket_companies = []
        search_queries = [
            f'"{bucket}" "pre-seed" OR "seed" startup',
            f'site:crunchbase.com/organization "{bucket}"'
        ]
        async with httpx.AsyncClient() as client:
            for query in search_queries:
                try:
                    response = await client.post(
                        'https://google.serper.dev/search', 
                        headers={'X-API-KEY': serper_api_key}, 
                        json={"q": query, "num": 10},
                        timeout=10.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    snippets = [r.get("snippet", "") + " " + r.get("title", "") for r in data.get("organic", [])]
                    
                    if snippets:
                        extraction_prompt = ChatPromptTemplate.from_messages([
                            ("system", "Extract a list of startup company names from the following search snippets. Return ONLY the company names."),
                            ("user", "Snippets: {snippets}")
                        ])
                        chain_extract = extraction_prompt | llm.with_structured_output(CompanyExtractionOutput)
                        res_extract = await chain_extract.ainvoke({"snippets": "\n".join(snippets)})
                        bucket_companies.extend(res_extract.companies)
                except Exception as e:
                    print(f"Error searching for bucket '{bucket}', query '{query}': {e}")
        return bucket_companies

    # Run searches concurrently
    results = await asyncio.gather(*(search_bucket(bucket) for bucket in micro_buckets))
    
    # Flatten and deduplicate
    for res in results:
        early_stage_companies.extend(res)
    
    discovered_companies = list(set([c for c in early_stage_companies if c]))
    print(f"Discovered {len(discovered_companies)} early-stage companies for {site.name}")

    # 3. Enrich and save to Neo4j
    sem = asyncio.Semaphore(5)
    
    async def enrich_and_save(company_name: str):
        async with sem:
            try:
                enriched = await enrich_company(company_name, site.name)
                if enriched:
                    await save_enriched_company_to_neo4j(str(site.id), enriched)
                    print(f"Successfully enriched and saved {company_name}")
            except Exception as e:
                print(f"Error enriching {company_name}: {e}")

    if discovered_companies:
        await asyncio.gather(*(enrich_and_save(company) for company in discovered_companies))
        
    print(f"Completed backfill for site: {site.name}")


async def main():
    print("Starting early-stage company backfill...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Site))
        sites = result.scalars().all()
        
        if not sites:
            print("No sites found in the database.")
            return
            
        print(f"Found {len(sites)} sites to backfill.")
        for site in sites:
            await backfill_site(site)
            
    print("Backfill complete.")

if __name__ == "__main__":
    asyncio.run(main())
