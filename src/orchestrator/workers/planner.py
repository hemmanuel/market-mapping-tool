from typing import List

from pydantic import BaseModel, Field

from src.agents.enrichment_agent import build_company_search_prompts
from src.api.events import event_manager
from src.orchestrator.core.llm import BespokeLLMClient
from src.orchestrator.core.schemas import PlanCompanySearchInput, PlanCompanySearchOutput, SearchQuerySpec, TaskFrame


class PlannerOutputModel(BaseModel):
    search_queries: List[str] = Field(description="List of specific search queries for the company")

class PlannerWorker:
    def __init__(self, llm_client: BespokeLLMClient):
        self.llm_client = llm_client

    async def execute(self, task: TaskFrame) -> PlanCompanySearchOutput:
        payload = PlanCompanySearchInput(**task.payload)
        niche = payload.niche
        company_name = payload.company_name
        pipeline_id = task.pipeline_id

        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Planner] Generating deep-dive search queries for: {company_name}"})

        system_prompt, prompt = build_company_search_prompts(company_name, niche)

        result = await self.llm_client.generate_structured(
            prompt=system_prompt + "\n\n" + prompt,
            response_schema=PlannerOutputModel
        )

        flat_queries: List[SearchQuerySpec] = []
        for query in result.search_queries:
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Planner] Generated query: '{query}'"})
            flat_queries.append(SearchQuerySpec(query=query, target_domains=[]))

        return PlanCompanySearchOutput(search_queries=flat_queries)
