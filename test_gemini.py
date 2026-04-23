import asyncio
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv('.env')

async def test():
    llm = ChatGoogleGenerativeAI(
        model=os.getenv('GEMINI_MODEL', 'gemini-3-flash-preview'), 
        api_key=os.getenv('GEMINI_API_KEY'),
        temperature=0.0
    )
    res = await llm.ainvoke('Hello')
    content = res.content
    if isinstance(content, list):
        content = ''.join([block.get('text', '') if isinstance(block, dict) else str(block) for block in content])
    print(repr(content))

asyncio.run(test())
