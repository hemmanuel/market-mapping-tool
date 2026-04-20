import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

async def main():
    url = os.getenv('POSTGRES_URL')
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT id, name FROM sites'))
        for row in result:
            print(f'ID: {row[0]}, Name: {row[1]}')
            
if __name__ == '__main__':
    asyncio.run(main())
