import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.neo4j_session import driver

async def remove_investor_insights():
    print("Removing investor_insight from all CanonicalEntity nodes...")
    
    query = """
    MATCH (c:CanonicalEntity)
    WHERE c.investor_insight IS NOT NULL
    REMOVE c.investor_insight
    RETURN count(c) as updated_count
    """
    
    try:
        async with driver.session() as session:
            result = await session.run(query)
            record = await result.single()
            updated_count = record["updated_count"] if record else 0
            print(f"Successfully removed investor_insight from {updated_count} nodes.")
    except Exception as e:
        print(f"Error during removal: {e}")
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(remove_investor_insights())