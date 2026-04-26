import os
import re

import httpx

from src.api.events import event_manager
from src.orchestrator.core.schemas import SearchQueryInput, SearchQueryOutput, TaskFrame


class SearchQueryWorker:
    def _extract_serper_error_message(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text
        return str(data.get("message") or data)

    def _build_query_variants(self, query: str) -> list[str]:
        variants: list[str] = []

        def add_variant(value: str) -> None:
            cleaned = re.sub(r"\s+", " ", value).strip()
            if cleaned and cleaned not in variants:
                variants.append(cleaned)

        add_variant(query)

        simplified = re.sub(r"\bOR\b", " ", query, flags=re.IGNORECASE)
        simplified = re.sub(r"[()\"]", " ", simplified)
        simplified = re.sub(r"\bfiletype:[A-Za-z0-9]+\b", " ", simplified, flags=re.IGNORECASE)
        add_variant(simplified)

        compressed = " ".join(simplified.split()[:14])
        add_variant(compressed)
        return variants

    async def execute(self, task: TaskFrame) -> SearchQueryOutput:
        payload = SearchQueryInput(**task.payload)
        pipeline_id = task.pipeline_id

        serper_api_key = os.getenv("SERPER_API_KEY")
        if not serper_api_key:
            raise RuntimeError("SERPER_API_KEY is not set")

        base_query = payload.query
        if payload.target_domains:
            domain_str = " OR ".join([f"site:{domain}" for domain in payload.target_domains])
            base_query = f"{base_query} ({domain_str})"

        headers = {
            "X-API-KEY": serper_api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            last_error: Exception | None = None
            for search_term in self._build_query_variants(base_query):
                await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Searcher] Executing search for: '{search_term}'"})
                try:
                    response = await client.post(
                        "https://google.serper.dev/search",
                        headers=headers,
                        json={"q": search_term, "num": 10},
                        timeout=10.0,
                    )
                    if response.status_code == 400:
                        message = self._extract_serper_error_message(response)
                        if "credit" in message.lower():
                            raise RuntimeError(f"Serper capacity error: {message}")
                        await event_manager.publish(
                            pipeline_id,
                            {"type": "log", "message": f"[Searcher] Serper rejected query, trying fallback form: '{search_term}' ({message})"},
                        )
                        continue

                    response.raise_for_status()
                    data = response.json()
                    urls = [result["link"] for result in data.get("organic", []) if "link" in result]

                    unique_urls: list[str] = []
                    for url in urls:
                        if url not in unique_urls:
                            unique_urls.append(url)

                    await event_manager.publish(
                        pipeline_id,
                        {"type": "log", "message": f"[Searcher] Found {len(unique_urls)} unique URLs for query '{payload.query}'."},
                    )
                    return SearchQueryOutput(urls=unique_urls)
                except Exception as exc:
                    last_error = exc
                    continue

        if last_error:
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Searcher] Search failed for '{payload.query}': {last_error}"})
            raise last_error

        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Searcher] No valid Serper query variant succeeded for '{payload.query}'."})
        return SearchQueryOutput(urls=[])
