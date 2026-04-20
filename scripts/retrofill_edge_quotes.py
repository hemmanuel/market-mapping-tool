import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.neo4j_session import driver

async def retrofill_edge_quotes():
    print("Starting retrofill of edge quotes for all existing graphs...")
    
    query = """
    MATCH (cs:CanonicalEntity)<-[:RESOLVES_TO]-(rs:RawEntity)-[r:RAW_RELATIONSHIP]->(rt:RawEntity)-[:RESOLVES_TO]->(ct:CanonicalEntity)
    WHERE cs <> ct
    WITH cs, ct, r.type AS rel_type, cs.pipeline_id AS pipeline_id, collect(r.exact_quote) AS quotes
    MATCH (cs)-[rel:INTERACTS_WITH {type: rel_type, pipeline_id: pipeline_id}]->(ct)
    SET rel.quotes = [q IN quotes WHERE q IS NOT NULL AND q <> ""]
    RETURN count(rel) as updated_count
    """
    
    try:
        async with driver.session() as session:
            result = await session.run(query)
            record = await result.single()
            updated_count = record["updated_count"] if record else 0
            print(f"Successfully updated {updated_count} INTERACTS_WITH edges with quotes.")
    except Exception as e:
        print(f"Error during retrofill: {e}")
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(retrofill_edge_quotes())
