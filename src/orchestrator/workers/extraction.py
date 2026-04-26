import os
import re
from typing import List

import httpx

from src.orchestrator.core.schemas import TaskFrame, ExtractCompaniesInput, ExtractCompaniesOutput
from src.orchestrator.core.llm import BespokeLLMClient
from src.api.events import event_manager

class CompanyExtractionWorker:
    def __init__(self, llm_client: BespokeLLMClient):
        self.llm_client = llm_client

    def _extract_serper_error_message(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text
        return str(data.get("message") or data)

    def _normalize_bucket_for_search(self, bucket: str) -> str:
        normalized = re.sub(r"[\"']", " ", bucket)
        normalized = re.sub(r"[()/:,]", " ", normalized)
        normalized = re.sub(r"\b20\d{2}(?:\s*-\s*20\d{2})?\b", " ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(
            r"\b(pre[- ]seed|seed stage|series a|series b|series c|late[- ]stage|growth[- ]stage)\b",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if len(normalized) > 90:
            normalized = normalized[:90].rsplit(" ", 1)[0].strip()
        return normalized or bucket

    def _build_search_queries(self, bucket: str) -> List[str]:
        normalized_bucket = self._normalize_bucket_for_search(bucket)
        return [
            f"{normalized_bucket} startup funding",
            f"{normalized_bucket} startup company",
            f"site:crunchbase.com/organization {normalized_bucket}",
        ]

    async def execute(self, task: TaskFrame) -> ExtractCompaniesOutput:
        payload = ExtractCompaniesInput(**task.payload)
        niche = payload.niche
        bucket = payload.micro_bucket
        pipeline_id = task.pipeline_id

        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[CompanyExtraction] Extracting companies for micro-bucket: {bucket}..."})

        # Task A: Memory-based extraction
        system_prompt = f"""You are an expert VC/PE analyst with deep knowledge of the {niche} market.
        List ALL known companies that fit perfectly into this specific micro-bucket: "{bucket}".
        Return ONLY the company names."""

        memory_companies = []
        try:
            res = await self.llm_client.generate_structured(
                prompt=system_prompt,
                response_schema=ExtractCompaniesOutput
            )
            memory_companies = res.companies
        except Exception as e:
            print(f"Error extracting companies for bucket {bucket}: {e}")

        # Task B: Active Search for Early-Stage
        serper_api_key = os.getenv("SERPER_API_KEY")
        if not serper_api_key:
            raise RuntimeError("SERPER_API_KEY is not set")
        search_queries = self._build_search_queries(bucket)
        
        early_stage_companies = []
        async with httpx.AsyncClient() as client:
            for query in search_queries:
                try:
                    response = await client.post(
                        'https://google.serper.dev/search',
                        headers={'X-API-KEY': serper_api_key, 'Content-Type': 'application/json'},
                        json={"q": query, "num": 10},
                        timeout=10.0
                    )
                    if response.status_code == 400:
                        message = self._extract_serper_error_message(response)
                        if "credit" in message.lower():
                            raise RuntimeError(f"Serper capacity error: {message}")
                        await event_manager.publish(
                            pipeline_id,
                            {"type": "log", "message": f"[CompanyExtraction] Serper rejected query, skipping: {query} ({message})"},
                        )
                        continue
                    response.raise_for_status()
                    data = response.json()
                    snippets = [r.get("snippet", "") + " " + r.get("title", "") for r in data.get("organic", [])]
                    
                    if snippets:
                        extraction_prompt = f"""Extract a list of startup company names from the following search snippets. Return ONLY the company names.
                        
                        Snippets:
                        {" ".join(snippets)}"""
                        
                        res_extract = await self.llm_client.generate_structured(
                            prompt=extraction_prompt,
                            response_schema=ExtractCompaniesOutput
                        )
                        early_stage_companies.extend(res_extract.companies)
                except Exception as e:
                    print(f"Error in active search for bucket {bucket}, query {query}: {e}")
                    raise

        combined_companies = list(set(memory_companies + early_stage_companies))
        
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[CompanyExtraction] Discovered {len(combined_companies)} unique companies in bucket: {bucket}."})

        return ExtractCompaniesOutput(companies=combined_companies)
