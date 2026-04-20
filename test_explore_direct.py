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
        
        # We need a valid token. Let's patch the endpoint temporarily to not require auth, or just look at the logs.
        # Wait, I can just run the python code directly!
        
        from src.api.routes import explore_node_group
        from src.db.session import AsyncSessionLocal
        
        # Mock db and user_id
        class MockDB:
            async def execute(self, *args, **kwargs):
                class MockResult:
                    def scalars(self):
                        class MockScalars:
                            def first(self):
                                class MockObj:
                                    id = site_id
                                    tenant_id = "mock_tenant"
                                return MockObj()
                        return MockScalars()
                return MockResult()
                
        try:
            res = await explore_node_group(site_id=site_id, node_id=str(node_id), db=MockDB(), user_id="mock_user")
            print(res)
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())