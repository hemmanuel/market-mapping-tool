import uuid
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy.future import select

from src.orchestrator.core.schemas import TaskFrame, VectorStorageInput, VectorStorageOutput
from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.models.relational import DataSource, Document as PGDocument


def _sanitize_text(value: str) -> str:
    return value.replace("\x00", "")


class VectorStorageWorker:
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=os.getenv("GEMINI_API_KEY"))

    async def execute(self, task: TaskFrame) -> VectorStorageOutput:
        payload = VectorStorageInput(**task.payload)
        raw_text = _sanitize_text(payload.raw_text)
        current_url = payload.url
        storage_object = payload.storage_object
        company_name = payload.company_name
        pipeline_id = task.pipeline_id
        document_ids: list[str] = []

        await event_manager.publish(pipeline_id, {"type": "log", "message": "[VectorStorage] Preparing to save chunks to PostgreSQL..."})
        
        if not raw_text:
            await event_manager.publish(pipeline_id, {"type": "log", "message": "[VectorStorage] Skipped: No raw text to process."})
            return VectorStorageOutput(stored_chunks=0, document_ids=[])
            
        # Chunk the text
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = splitter.split_text(raw_text)
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Split text into {len(chunks)} chunks."})
        
        if not chunks:
            return VectorStorageOutput(stored_chunks=0, document_ids=[])
            
        # Generate embeddings
        try:
            chunk_embeddings = await self.embeddings.aembed_documents(chunks)
        except Exception as e:
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Failed to generate embeddings: {e}"})
            print(f"Failed to embed chunks: {e}")
            return VectorStorageOutput(stored_chunks=0, document_ids=[])
            
        stored_chunks = 0
        
        async with AsyncSessionLocal() as session:
            try:
                # Find a data source for this pipeline (site)
                result = await session.execute(select(DataSource).where(DataSource.site_id == pipeline_id).limit(1))
                data_source = result.scalars().first()
                
                if not data_source:
                    data_source = DataSource(
                        site_id=pipeline_id,
                        source_type="web_search",
                        name="Autonomous Web Search",
                        config={}
                    )
                    session.add(data_source)
                    await session.flush()
                    
                for i, chunk in enumerate(chunks):
                    metadata_json = {
                        "source_url": current_url,
                        "chunk_index": i,
                        "storage_object": storage_object,
                    }
                    if company_name:
                        metadata_json["company_name"] = company_name
                        metadata_json["company_names"] = [company_name]
                    doc = PGDocument(
                        id=uuid.uuid4(),
                        data_source_id=data_source.id,
                        title=f"Extracted from {current_url} (Chunk {i+1})",
                        raw_text=chunk,
                        embedding=chunk_embeddings[i],
                        metadata_json=metadata_json,
                    )
                    session.add(doc)
                    stored_chunks += 1
                    document_ids.append(str(doc.id))
                    
                await session.commit()
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Saved {stored_chunks} embedded chunks to PostgreSQL."})
                
                # Publish new_chunk event for the first chunk to show in the UI
                if chunks:
                    await event_manager.publish(pipeline_id, {
                        "type": "new_chunk", 
                        "data": {
                            "source": current_url, 
                            "text_snippet": chunks[0][:200] + "..."
                        }
                    })
                
            except Exception as e:
                await session.rollback()
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[VectorStorage] Database error: {e}"})
                print(f"Database error in VectorStorage: {e}")
                
        return VectorStorageOutput(stored_chunks=stored_chunks, document_ids=document_ids)
