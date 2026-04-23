import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from src.db.session import AsyncSessionLocal

async def main():
    print("Connecting...")
    async with AsyncSessionLocal() as session:
        print("Connected!")

if __name__ == "__main__":
    asyncio.run(main())