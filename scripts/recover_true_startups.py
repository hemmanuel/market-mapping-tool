import asyncio
import os
import sys
from dotenv import load_dotenv

print("Script started!")

# Add project root to PYTHONPATH so imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from src.db.session import AsyncSessionLocal
from src.models.relational import Site
from sqlalchemy.future import select
from src.agents.nodes import market_sizing_node, CompanyExtractionOutput
from src.agents.enrichment_agent import enrich_company
from src.agents.neo4j_enrichment import save_enriched_company_to_neo4j
from src.db.neo4j_session import driver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

async def main():
    pipeline_id = 'd1320f27-669e-4216-a311-8f51d97ac8de' # Your existing pipeline
    
    print("Connecting to DB...")
    async with AsyncSessionLocal() as session:
        print("Connected to DB. Executing query...")
        result = await session.execute(select(Site).where(Site.id == pipeline_id))
        print("Query executed. Fetching result...")
        site = result.scalars().first()
        if not site:
            print("Pipeline not found in Postgres.")
            return
        niche = site.name
        print(f"Targeting Pipeline: {niche} ({pipeline_id})")

    # 1. Run the Market Sizing Node to get micro-buckets
    state = {"pipeline_id": pipeline_id, "niche": niche}
    print("\n--- Phase 1: Market Sizing (Finding Micro-Buckets) ---")
    state = await market_sizing_node(state)
    micro_buckets = state.get('micro_buckets', [])
    
    print(f"\nFound {len(micro_buckets)} micro-buckets.")
    
    # Save micro-buckets to Neo4j
    print("Saving micro-buckets to Neo4j...")
    async with driver.session() as neo4j_session:
        for bucket in micro_buckets:
            await neo4j_session.run(
                """
                MERGE (b:MicroBucket {name: $bucket, pipeline_id: $pipeline_id})
                """,
                bucket=bucket,
                pipeline_id=pipeline_id
            )
    print("Micro-buckets saved.")

    # 2. Run the Company Extraction Node to get the exhaustive list of true startups
    print("\n--- Phase 2: Exhaustive Startup Extraction ---")
    
    llm = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"), api_key=os.getenv("GEMINI_API_KEY"), temperature=0.0)
    
    async def extract_companies_for_bucket(bucket: str):
        print(f"Extracting companies for bucket: {bucket}")
        system_prompt = f"""You are an expert VC/PE analyst with deep knowledge of the {niche} market.
        List ALL known companies that fit perfectly into this specific micro-bucket: "{bucket}".
        Return ONLY the company names."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Bucket: {bucket}")
        ])
        
        chain = prompt | llm.with_structured_output(CompanyExtractionOutput)
        try:
            res = await chain.ainvoke({"bucket": bucket})
            print(f"Found {len(res.companies)} companies for bucket: {bucket}")
            return res.companies
        except Exception as e:
            print(f"Error extracting companies for bucket {bucket}: {e}")
            return []

    # Run extractions concurrently
    results = await asyncio.gather(*(extract_companies_for_bucket(bucket) for bucket in micro_buckets))
    
    # Flatten and deduplicate
    discovered_companies = list(set([company for sublist in results for company in sublist if company]))
    
    print(f"\n--- Phase 3: Discovered {len(discovered_companies)} True Startups! ---")
    
    # 3. Deep Enrichment
    print("\n--- Phase 4: Deep VC Enrichment ---")
    sem = asyncio.Semaphore(2) # Limit concurrency to avoid rate limits (lowered to 2 to be kinder to Serper)
    
    async def process_company(company_name: str):
        async with sem:
            try:
                enriched = await enrich_company(company_name, niche)
                if enriched:
                    await save_enriched_company_to_neo4j(pipeline_id, enriched)
                else:
                    print(f"Failed to enrich: {company_name}")
            except Exception as e:
                print(f"Unhandled error processing {company_name}: {e}")

    # Run enrichment concurrently for all discovered companies
    await asyncio.gather(*(process_company(company) for company in discovered_companies))
    
    # 4. Cleanup old garbage nodes
    print("\n--- Phase 5: Cleaning up old generic 'Company' nodes ---")
    async with driver.session() as neo4j_session:
        res = await neo4j_session.run(
            """
            MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id, type: 'Company'})
            DETACH DELETE c
            RETURN count(c) as deleted_count
            """,
            pipeline_id=pipeline_id
        )
        deleted = (await res.single())['deleted_count']
        print(f"Deleted {deleted} old generic 'Company' nodes.")
        
    print("\nRecovery and Enrichment Complete! Check your graph.")

if __name__ == '__main__':
    asyncio.run(main())
