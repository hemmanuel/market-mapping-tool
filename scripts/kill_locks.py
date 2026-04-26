import asyncio
from sqlalchemy import text
from src.db.session import AsyncSessionLocal

async def kill():
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid()"))
        await session.commit()
        print('Killed other connections')

if __name__ == '__main__':
    asyncio.run(kill())