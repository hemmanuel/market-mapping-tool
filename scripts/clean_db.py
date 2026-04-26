import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import delete
from src.db.session import AsyncSessionLocal
from src.models.relational import Document, PendingDocument, DataSource, Site
from src.db.neo4j_session import driver
from src.services.storage import storage

async def clean_database():
    print("Connecting to the database to clean truncated data...")
    
    # 1. Clean PostgreSQL
    async with AsyncSessionLocal() as session:
        try:
            print("Deleting PostgreSQL Documents...")
            await session.execute(delete(Document))
            
            print("Deleting PostgreSQL PendingDocuments...")
            await session.execute(delete(PendingDocument))
            
            print("Deleting PostgreSQL DataSources...")
            await session.execute(delete(DataSource))
            
            print("Deleting PostgreSQL Sites...")
            await session.execute(delete(Site))
            
            await session.commit()
            print("PostgreSQL successfully cleaned!")
            
        except Exception as e:
            await session.rollback()
            print(f"An error occurred during PostgreSQL cleanup: {e}")

    # 2. Clean Neo4j
    try:
        print("Deleting Neo4j Graph Data...")
        async with driver.session() as neo4j_session:
            await neo4j_session.run("MATCH (n) DETACH DELETE n")
        print("Neo4j successfully cleaned!")
    except Exception as e:
        print(f"An error occurred during Neo4j cleanup: {e}")

    # 3. Clean MinIO
    try:
        print("Deleting MinIO Objects...")
        bucket_name = storage.bucket_name
        if storage.client.bucket_exists(bucket_name):
            objects_to_delete = storage.client.list_objects(bucket_name, recursive=True)
            for obj in objects_to_delete:
                storage.client.remove_object(bucket_name, obj.object_name)
            print("MinIO successfully cleaned!")
        else:
            print("MinIO bucket does not exist, skipping.")
    except Exception as e:
        print(f"An error occurred during MinIO cleanup: {e}")

if __name__ == "__main__":
    asyncio.run(clean_database())
