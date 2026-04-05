import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

POSTGRES_URL = os.getenv("POSTGRES_URL")

if not POSTGRES_URL:
    raise ValueError("POSTGRES_URL environment variable is not set. Cannot initialize database connection.")

# Create the async engine
# pool_pre_ping ensures connections are alive before using them (crucial for long-running ingestion pipelines)
engine = create_async_engine(
    POSTGRES_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Create a configured "Session" class
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db_session() -> AsyncSession:
    """
    Dependency function to get a database session.
    Useful for FastAPI injection or context managers in background workers.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
