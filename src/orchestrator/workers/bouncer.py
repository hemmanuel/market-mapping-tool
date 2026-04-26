import re
from urllib.parse import urlparse

from src.api.events import event_manager
from src.orchestrator.core.schemas import BouncerInput, BouncerOutput, TaskFrame


STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "their", "about",
    "focus", "early", "stage", "stages", "emerging", "technologies", "technology", "independent",
    "operator", "system", "systems", "body", "group", "capital", "firm", "institution", "agency",
}


def _normalize_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _tokenize(value: str) -> list[str]:
    normalized = _normalize_text(value)
    return [token for token in normalized.split() if len(token) >= 3 and token not in STOPWORDS]

class BouncerWorker:
    async def execute(self, task: TaskFrame) -> BouncerOutput:
        payload = BouncerInput(**task.payload)
        raw_text = payload.raw_text
        current_url = payload.url
        niche = payload.niche
        entities = payload.schema_entities
        company_name = payload.company_name or ""
        pipeline_id = task.pipeline_id

        await event_manager.publish(pipeline_id, {"type": "log", "message": "[Bouncer] Evaluating text relevance with company-aware heuristics..."})
        
        if not raw_text:
            await event_manager.publish(pipeline_id, {"type": "log", "message": "[Bouncer] Rejected: No text to evaluate"})
            return BouncerOutput(is_relevant=False, relevance_reason="No text to evaluate")
            
        if len(raw_text) < 200:
            await event_manager.publish(pipeline_id, {"type": "log", "message": "[Bouncer] Rejected: Text too short (< 200 chars)"})
            return BouncerOutput(is_relevant=False, relevance_reason="Text too short")
            
        normalized_text = _normalize_text(raw_text)
        normalized_url = _normalize_text(f"{urlparse(current_url).netloc} {urlparse(current_url).path}")

        company_phrase = _normalize_text(company_name)
        company_tokens = _tokenize(company_name)
        niche_tokens = list(dict.fromkeys(_tokenize(niche)))[:8]

        entity_tokens: list[str] = []
        for entity in entities:
            entity_tokens.extend(_tokenize(entity))
        entity_tokens = list(dict.fromkeys(entity_tokens))[:12]

        company_phrase_hits = normalized_text.count(company_phrase) if company_phrase else 0
        company_token_hits = sum(normalized_text.count(token) for token in company_tokens)
        url_company_hits = sum(normalized_url.count(token) for token in company_tokens)
        niche_hits = sum(normalized_text.count(token) for token in niche_tokens)
        entity_hits = sum(normalized_text.count(token) for token in entity_tokens)

        approved = False
        if company_phrase_hits >= 1:
            approved = True
        elif url_company_hits >= max(1, len(company_tokens) // 2) and (company_token_hits >= 1 or niche_hits >= 2):
            approved = True
        elif company_token_hits >= max(2, len(company_tokens)) and (niche_hits >= 2 or entity_hits >= 2):
            approved = True

        if not approved:
            reason = (
                "Low relevance: "
                f"company_phrase_hits={company_phrase_hits}, "
                f"company_token_hits={company_token_hits}, "
                f"url_company_hits={url_company_hits}, "
                f"niche_hits={niche_hits}, "
                f"entity_hits={entity_hits}."
            )
            await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Bouncer] Rejected: {reason}"})
            return BouncerOutput(is_relevant=False, relevance_reason=reason)
            
        reason = (
            "Approved: "
            f"company_phrase_hits={company_phrase_hits}, "
            f"company_token_hits={company_token_hits}, "
            f"url_company_hits={url_company_hits}, "
            f"niche_hits={niche_hits}, "
            f"entity_hits={entity_hits}."
        )
        await event_manager.publish(pipeline_id, {"type": "log", "message": f"[Bouncer] {reason}"})
        
        return BouncerOutput(is_relevant=True, relevance_reason=reason)
