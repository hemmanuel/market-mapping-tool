import asyncio
import os
from src.agents.enrichment_agent import enrich_company
from src.agents.neo4j_enrichment import save_enriched_company_to_neo4j
from dotenv import load_dotenv

load_dotenv()

async def main():
    pipeline_id = 'test-pipeline-id-123'
    company_name = 'Fischer Block'
    niche = 'Electric Power Grid Modernization'
    
    print(f"Testing enrichment and Neo4j storage for {company_name}...")
    result = await enrich_company(company_name, niche)
    
    if result:
        print("\n--- Enrichment Successful, saving to Neo4j ---")
        await save_enriched_company_to_neo4j(pipeline_id, result)
        print("Test complete.")
    else:
        print("Enrichment failed.")

if __name__ == '__main__':
    asyncio.run(main())
