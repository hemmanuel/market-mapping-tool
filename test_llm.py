import os
from langchain_google_genai import ChatGoogleGenerativeAI

try:
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key="dummy_key", temperature=0.0)
    print("Success")
except Exception as e:
    print(f"Error: {e}")