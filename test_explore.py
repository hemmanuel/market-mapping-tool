import asyncio
import sys
import os
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.db.neo4j_session import driver

async def test():
    async with driver.session() as session:
        result = await session.run("MATCH (c:CanonicalEntity) RETURN c.pipeline_id as site_id, id(c) as node_id LIMIT 1")
        record = await result.single()
        if not record:
            print("No nodes found")
            return
        site_id = record["site_id"]
        node_id = record["node_id"]
        
        print(f"Testing site_id={site_id}, node_id={node_id}")
        
        resp = requests.get(f"http://host.docker.internal:8000/api/v1/pipelines/{site_id}/nodes/{node_id}/explore")
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    asyncio.run(test())