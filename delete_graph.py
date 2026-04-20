import asyncio
import os
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

load_dotenv()

async def main():
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    pipeline_id = '771ccbbd-8f44-44c7-bb9e-b008bbb91c8b'
    
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    async with driver.session() as session:
        print(f"Deleting graph data for pipeline: {pipeline_id}")
        
        # Delete relationships first
        await session.run(
            """
            MATCH ()-[r {pipeline_id: $pipeline_id}]->()
            DELETE r
            """,
            pipeline_id=pipeline_id
        )
        
        # Delete nodes
        await session.run(
            """
            MATCH (n {pipeline_id: $pipeline_id})
            DETACH DELETE n
            """,
            pipeline_id=pipeline_id
        )
        
        print("Deletion complete.")
        
    await driver.close()

if __name__ == '__main__':
    asyncio.run(main())
