import asyncio
import sys

# Add the project root to the Python path
sys.path.append('/app')

from src.services.rag_service import generate_rag_insight

async def test_rag():
    pipeline_id = "771ccbbd-8f44-44c7-bb9e-b008bbb91c8b"
    target_id = 337013
    target_type = "Entity"
    
    print(f"Testing RAG service for {target_type} ID: {target_id} in pipeline: {pipeline_id}")
    
    insight = await generate_rag_insight(pipeline_id, target_id, target_type)
    
    print("\n--- RAG INSIGHT ---")
    print(insight)
    print("-------------------\n")

if __name__ == "__main__":
    asyncio.run(test_rag())