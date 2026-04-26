from src.orchestrator.core.schemas import TaskFrame, MarketSizingInput, MarketSizingOutput
from src.orchestrator.core.llm import BespokeLLMClient
from src.api.events import event_manager

class MarketSizingWorker:
    def __init__(self, llm_client: BespokeLLMClient):
        self.llm_client = llm_client

    async def execute(self, task: TaskFrame) -> MarketSizingOutput:
        payload = MarketSizingInput(**task.payload)
        niche = payload.niche
        pipeline_id = task.pipeline_id

        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[MarketSizing] Estimating market scale and generating micro-buckets for: {niche}"})

        system_prompt = f"""You are a Market Sizing Expert. Your goal is to help exhaustively map a market niche by breaking it down into small, highly specific "micro-buckets".
        
        First, estimate the total number of active VC-backed startups and mature companies in the niche across all stages (Seed, Series A, Series B, Late, Public).
        Then, fracture the market into specific micro-buckets (by geography, sub-niche, or vintage) such that EACH bucket likely contains fewer than 50 companies.
        
        Example micro-buckets:
        - "Seed stage Electric Power startups in North America funded in 2023"
        - "Series A Grid Storage companies in Europe"
        - "Late-stage Virtual Power Plant companies"
        
        Return a comprehensive list of these micro-buckets.
        
        Niche: {niche}"""

        result = await self.llm_client.generate_structured(
            prompt=system_prompt,
            response_schema=MarketSizingOutput
        )

        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[MarketSizing] Generated {len(result.micro_buckets)} micro-buckets for exhaustive extraction."})

        return result
