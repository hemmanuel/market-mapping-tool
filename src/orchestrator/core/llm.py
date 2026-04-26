import os
import json
import asyncio
import httpx
from typing import Type, TypeVar, Any
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

T = TypeVar('T', bound=BaseModel)

class BespokeLLMClient:
    def __init__(self, model: str = None, api_key: str = None):
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    async def generate_structured(self, prompt: str, response_schema: Type[T], max_retries: int = 3) -> T:
        """
        Generates structured output from the LLM based on the provided Pydantic schema.
        Includes deterministic exponential backoff for 429s, 500s, and JSON parsing errors.
        """
        schema_dict = response_schema.model_json_schema()
        definitions = schema_dict.get("$defs", {})

        # Convert JSON schema to Gemini's expected format.
        # Gemini expects 'type' to be uppercase strings like 'OBJECT', 'STRING', 'ARRAY'.
        def convert_schema(schema: dict) -> dict:
            if "$ref" in schema:
                ref = schema["$ref"]
                if ref.startswith("#/$defs/"):
                    ref_name = ref.split("/")[-1]
                    return convert_schema(definitions.get(ref_name, {}))
                return {}

            if "anyOf" in schema:
                non_null_options = [option for option in schema["anyOf"] if option.get("type") != "null"]
                if len(non_null_options) == 1:
                    converted = convert_schema(non_null_options[0])
                    if "description" in schema and "description" not in converted:
                        converted["description"] = schema["description"]
                    return converted
                if non_null_options:
                    return convert_schema(non_null_options[0])
                return {}

            new_schema = {}
            schema_type = schema.get("type")
            if isinstance(schema_type, str):
                new_schema["type"] = schema_type.upper()

            if "properties" in schema:
                new_schema["properties"] = {
                    key: convert_schema(value) for key, value in schema["properties"].items()
                }
            if "items" in schema:
                new_schema["items"] = convert_schema(schema["items"])
            if "required" in schema:
                new_schema["required"] = schema["required"]
            if "description" in schema:
                new_schema["description"] = schema["description"]
            if "enum" in schema:
                new_schema["enum"] = schema["enum"]
            if "additionalProperties" in schema and isinstance(schema["additionalProperties"], dict):
                new_schema["additionalProperties"] = convert_schema(schema["additionalProperties"])
            return new_schema

        gemini_schema = convert_schema(schema_dict)

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": gemini_schema
            }
        }

        headers = {
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}?key={self.api_key}"

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, headers=headers, json=payload, timeout=30.0)
                    
                    if response.status_code in [429, 500, 502, 503, 504]:
                        raise httpx.HTTPStatusError(f"Server error: {response.status_code}", request=response.request, response=response)
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    if "candidates" not in data or not data["candidates"]:
                        raise ValueError("No candidates returned from LLM.")
                        
                    text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # Parse JSON and validate with Pydantic
                    parsed_json = json.loads(text_response)
                    return response_schema.model_validate(parsed_json)
                    
            except (httpx.HTTPStatusError, httpx.RequestError, ValueError, json.JSONDecodeError) as e:
                if attempt == max_retries - 1:
                    print(f"LLM call failed after {max_retries} attempts: {e!r}")
                    raise
                
                # Exponential backoff: 2, 4, 8 seconds
                sleep_time = 2 ** (attempt + 1)
                print(f"LLM call failed: {e!r}. Retrying in {sleep_time} seconds...")
                await asyncio.sleep(sleep_time)
