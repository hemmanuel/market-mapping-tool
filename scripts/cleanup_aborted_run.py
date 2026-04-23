import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from src.db.neo4j_session import driver

async def cleanup():
    pipeline_id = 'd1320f27-669e-4216-a311-8f51d97ac8de'
    print(f"Cleaning up aborted run data for pipeline: {pipeline_id}")
    
    async with driver.session() as session:
        # 1. Delete MicroBuckets
        res_buckets = await session.run(
            """
            MATCH (m:MicroBucket {pipeline_id: $pipeline_id})
            DETACH DELETE m
            RETURN count(m) as deleted_count
            """,
            pipeline_id=pipeline_id
        )
        deleted_buckets = (await res_buckets.single())['deleted_count']
        print(f"Deleted {deleted_buckets} MicroBucket nodes.")

        # 2. Delete newly enriched companies. 
        # We identify them by checking for properties unique to the new enrichment schema (e.g., 'business_model' or 'stage_estimate')
        res_companies = await session.run(
            """
            MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
            WHERE c.business_model IS NOT NULL OR c.stage_estimate IS NOT NULL
            DETACH DELETE c
            RETURN count(c) as deleted_count
            """,
            pipeline_id=pipeline_id
        )
        deleted_companies = (await res_companies.single())['deleted_count']
        print(f"Deleted {deleted_companies} newly enriched company nodes.")

if __name__ == "__main__":
    asyncio.run(cleanup())