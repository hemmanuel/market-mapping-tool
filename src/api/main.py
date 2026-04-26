from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router as pipelines_router
from src.services.storage import storage

app = FastAPI(
    title="Market Intelligence PaaS API",
    description="Backend API for Market Mapping Tool",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    storage.ensure_bucket_exists()

# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://market-mapping-tool.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(pipelines_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
