import asyncio
import os
from typing import Any, Iterable, Sequence

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from src.agents.schemas.enrichment import CompanyEnrichment

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
    api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.0,
)


def build_company_search_prompts(company_name: str, niche: str) -> tuple[str, str]:
    system_prompt = f"""You are a Master Sourcing Strategist.

Your goal is to plan a durable, front-door-compatible evidence set for a company enrichment workflow.

Return ONLY a JSON object with one field: `search_queries`, which must be an array of search query strings.

Generate 6 to 10 targeted search queries for "{company_name}" in the "{niche}" niche.

Prioritize durable primary or near-primary evidence that can survive front-door ingestion:
- official website, product pages, technical documentation, case studies
- team/about/founder pages
- investor, funding, or launch announcements
- customer, partner, or deployment evidence
- PDF, PPTX, DOCX, and other document-heavy sources when relevant

Use advanced operators like `site:`, `filetype:`, and `intitle:` when they increase source quality.
Avoid generic vanity queries with weak evidence density.
"""
    prompt = f"Niche: {niche}\nCompany: {company_name}"
    return system_prompt, prompt


def _dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        cleaned = (value or "").strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _truncate(value: str, limit: int = 4000) -> str:
    cleaned = (value or "").replace("\x00", "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def format_enrichment_evidence(
    company_name: str,
    niche: str,
    evidence_records: Sequence[dict[str, Any]],
    *,
    max_records: int = 18,
    max_chars_per_record: int = 4000,
) -> str:
    lines = [
        f"COMPANY NAME: {company_name}",
        f"INDUSTRY/NICHE: {niche}",
        "",
    ]

    for index, record in enumerate(evidence_records[:max_records], start=1):
        source_url = record.get("source_url") or "Unknown"
        title = record.get("title") or f"Evidence {index}"
        raw_text = _truncate(str(record.get("raw_text") or ""), max_chars_per_record)
        lines.extend(
            [
                f"--- EVIDENCE {index} ---",
                f"URL: {source_url}",
                f"TITLE: {title}",
                f"TEXT:",
                raw_text,
                "",
            ]
        )

    return "\n".join(lines)


def extract_enrichment_source_urls(evidence_records: Sequence[dict[str, Any]]) -> list[str]:
    return _dedupe_preserving_order(str(record.get("source_url") or "") for record in evidence_records)


async def synthesize_company_enrichment(
    company_name: str,
    niche: str,
    evidence_records: Sequence[dict[str, Any]],
) -> CompanyEnrichment:
    if not evidence_records:
        raise ValueError("Cannot synthesize enrichment without evidence records")

    gathered_text = format_enrichment_evidence(company_name, niche, evidence_records)
    source_urls = extract_enrichment_source_urls(evidence_records)

    system_prompt = f"""You are an elite Venture Capital Analyst specializing in the {niche} sector.

You are enriching a company named "{company_name}" from stored evidence that has already been ingested through the platform's durable front door.

Your task is to synthesize this evidence into a structured VC dossier that matches the provided schema exactly.

CRITICAL INSTRUCTIONS:
1. Use only the supplied evidence. Do not invent outside facts or rely on unstated external knowledge.
2. Be analytical and objective. Do not copy marketing fluff verbatim.
3. If exact funding numbers or dates are missing, use "Undisclosed" or a clearly labeled estimate such as "Seed (Est.)".
4. For `dimension_scores`, infer reasonable 0.0 to 1.0 scores from the available evidence.
5. For `strategic_analysis` and `metric_rationales`, write concise but insightful reasoning grounded in the evidence.
6. In `vc_dossier.source_urls`, include only URLs that appear in the evidence.
7. If the company appears to be an incumbent, utility, investor, or irrelevant noise rather than a startup, still fill out the schema and set `stage_estimate` appropriately.
"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", "Stored Evidence:\n\n{context}"),
        ]
    )
    structured_llm = llm.with_structured_output(CompanyEnrichment)
    chain = prompt | structured_llm

    max_llm_retries = 5
    for attempt in range(max_llm_retries):
        try:
            result = await chain.ainvoke({"context": gathered_text})
            result.vc_dossier.source_urls = _dedupe_preserving_order(
                list(result.vc_dossier.source_urls) + source_urls
            )
            return result
        except Exception as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                wait_time = 2 ** attempt
                print(
                    f"Gemini 429 Too Many Requests for {company_name}. "
                    f"Retrying in {wait_time}s (Attempt {attempt + 1}/{max_llm_retries})..."
                )
                await asyncio.sleep(wait_time)
                continue
            raise

    raise RuntimeError(f"Exhausted Gemini retries for company enrichment: {company_name}")
