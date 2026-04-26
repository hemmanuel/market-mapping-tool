#!/usr/bin/env python3
"""Bulk local graph extraction for the bespoke corpus."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert


DEFAULT_SITE_ID = "d9f940ea-982c-4a04-8c6b-2d653457cf9a"
DEFAULT_POSTGRES_URL = "postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db"
DEFAULT_MODEL_URL = "http://localhost:8001/v1/chat/completions"
DEFAULT_MODEL = "NousResearch/Hermes-3-Llama-3.1-8B"

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("POSTGRES_URL", DEFAULT_POSTGRES_URL)

from src.db.session import AsyncSessionLocal  # noqa: E402
from src.models.relational import DataSource, Document as PGDocument, Site  # noqa: E402
from src.orchestrator.core.graph_models import GraphEntityFact, GraphRelationshipFact  # noqa: E402
from src.orchestrator.core.graph_store import (  # noqa: E402
    build_graph_entity_fact_key,
    build_graph_relationship_fact_key,
    normalize_graph_name,
)
from src.orchestrator.core.ledger_models import (  # noqa: E402
    OrchestrationTaskFrameRecord,
    PipelineRun,
    TaskAttempt,
    WorkflowContext,
    utcnow,
)


EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence_text": {"type": "string"},
                },
                "required": ["name", "type"],
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string"},
                    "exact_quote": {"type": "string"},
                    "source_type": {"type": "string"},
                    "target_type": {"type": "string"},
                },
                "required": ["source", "target", "type", "exact_quote"],
            },
        },
    },
    "required": ["entities", "relationships"],
}

SYSTEM_PROMPT = """You are a high-throughput market-intelligence graph extraction engine.

Extract only facts supported by the text. Prefer concrete entities useful for market topology:
companies, investors, founders, executives, technologies, products, assets, basins, regulators,
agencies, standards, contracts, partnerships, acquisitions, funding events, and market concepts.

Rules:
- Return JSON only.
- Do not invent facts.
- Ignore page chrome, navigation, boilerplate, cookie text, and generic disclaimers.
- For each entity, provide `name`, `type`, optional `description`, and optional `evidence_text`.
- For each relationship, provide `source`, `target`, `type`, and an `exact_quote` copied verbatim from the text.
- If a relationship is not proven by a short exact quote, do not include it.
- Include relationship endpoint entities in `entities` whenever possible.
"""


@dataclass(slots=True)
class DocumentJob:
    document_id: str
    title: str | None
    source_url: str | None
    chunk_index: int | None
    raw_text: str


@dataclass(slots=True)
class ExtractionResult:
    document: DocumentJob
    payload: dict[str, Any] | None
    error: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _bounded(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _checkpoint_path(run_id: str, explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path)
    return Path(".server-state") / f"bulk_graph_extract_{run_id}.jsonl"


def _load_checkpoint(path: Path) -> set[str]:
    processed: set[str] = set()
    if not path.exists():
        return processed
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            document_id = record.get("document_id")
            if isinstance(document_id, str) and record.get("ok") is True:
                processed.add(document_id)
    return processed


def _append_checkpoint(path: Path, result: ExtractionResult, entity_count: int, relationship_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "document_id": result.document.document_id,
                    "source_url": result.document.source_url,
                    "ok": result.error is None,
                    "error": result.error,
                    "entity_count": entity_count,
                    "relationship_count": relationship_count,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=True,
            )
            + "\n"
        )


async def _ensure_bulk_run(site_id: str, run_id: str | None, reset_existing_run: bool) -> tuple[str, str, str]:
    site_uuid = uuid.UUID(site_id)
    async with AsyncSessionLocal() as session:
        site = await session.get(Site, site_uuid)
        if site is None:
            raise RuntimeError(f"Site {site_id} does not exist in the configured Postgres database.")

        run_uuid = uuid.UUID(run_id) if run_id else uuid.uuid4()
        if run_id:
            run = await session.get(PipelineRun, run_uuid)
            if run is None:
                raise RuntimeError(f"Run {run_id} does not exist. Omit --run-id to create a bulk run.")
            run.status = "running"
            run.updated_at = utcnow()
            if reset_existing_run:
                await session.execute(
                    GraphRelationshipFact.__table__.delete().where(GraphRelationshipFact.run_id == run_uuid)
                )
                await session.execute(GraphEntityFact.__table__.delete().where(GraphEntityFact.run_id == run_uuid))
        else:
            run = PipelineRun(
                id=run_uuid,
                site_id=site_uuid,
                status="running",
                objective="bulk_graph_extract",
                started_at=utcnow(),
            )
            session.add(run)
            session.add(
                WorkflowContext(
                    run_id=run_uuid,
                    site_id=site_uuid,
                    context_json={"niche": site.name, "source": "bulk_local_graph_extract"},
                )
            )

        task_result = await session.execute(
            select(OrchestrationTaskFrameRecord).where(
                OrchestrationTaskFrameRecord.run_id == run_uuid,
                OrchestrationTaskFrameRecord.task_type == "BULK_GRAPH_FACT_EXTRACTION",
                OrchestrationTaskFrameRecord.idempotency_key == "seed:BULK_GRAPH_FACT_EXTRACTION",
            )
        )
        task = task_result.scalars().first()
        if task is None:
            task = OrchestrationTaskFrameRecord(
                run_id=run_uuid,
                site_id=site_uuid,
                task_type="BULK_GRAPH_FACT_EXTRACTION",
                payload_json={"site_id": site_id, "run_id": str(run_uuid)},
                priority=200,
                concurrency_class="llm",
                idempotency_key="seed:BULK_GRAPH_FACT_EXTRACTION",
                status="in_progress",
                started_at=utcnow(),
                lease_owner="bulk-local-extract",
            )
            session.add(task)
            await session.flush()
        else:
            task.status = "in_progress"
            task.outcome = None
            task.completed_at = None
            task.lease_owner = "bulk-local-extract"
            task.heartbeat_at = utcnow()

        attempt_result = await session.execute(
            select(TaskAttempt).where(TaskAttempt.task_frame_id == task.id, TaskAttempt.attempt_number == 1)
        )
        attempt = attempt_result.scalars().first()
        if attempt is None:
            attempt = TaskAttempt(
                task_frame_id=task.id,
                run_id=run_uuid,
                site_id=site_uuid,
                attempt_number=1,
                status="started",
                worker_version="bulk-local-v1",
                lease_owner="bulk-local-extract",
            )
            session.add(attempt)
            await session.flush()
        else:
            attempt.status = "started"
            attempt.outcome = None
            attempt.finished_at = None
            attempt.error_code = None
            attempt.error_payload = None
            attempt.heartbeat_at = utcnow()
            attempt.lease_owner = "bulk-local-extract"

        await session.commit()
        return str(run_uuid), str(task.id), str(attempt.id)


async def _count_documents(site_id: str) -> int:
    site_uuid = uuid.UUID(site_id)
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(PGDocument)
                .join(DataSource, PGDocument.data_source_id == DataSource.id)
                .where(DataSource.site_id == site_uuid)
            )
            or 0
        )


async def _document_batches(
    *,
    site_id: str,
    processed_ids: set[str],
    fetch_size: int,
    limit: int | None,
) -> Any:
    site_uuid = uuid.UUID(site_id)
    yielded = 0
    offset = 0
    while True:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PGDocument.id, PGDocument.title, PGDocument.raw_text, PGDocument.metadata_json)
                .join(DataSource, PGDocument.data_source_id == DataSource.id)
                .where(DataSource.site_id == site_uuid)
                .order_by(PGDocument.processed_at.asc(), PGDocument.id.asc())
                .offset(offset)
                .limit(fetch_size)
            )
            rows = result.all()

        if not rows:
            break

        batch: list[DocumentJob] = []
        for document_id, title, raw_text, metadata_json in rows:
            offset += 1
            doc_id = str(document_id)
            if doc_id in processed_ids or not raw_text:
                continue
            metadata = metadata_json if isinstance(metadata_json, dict) else {}
            batch.append(
                DocumentJob(
                    document_id=doc_id,
                    title=title,
                    source_url=metadata.get("source_url"),
                    chunk_index=metadata.get("chunk_index"),
                    raw_text=raw_text,
                )
            )
            yielded += 1
            if limit is not None and yielded >= limit:
                yield batch
                return

        if batch:
            yield batch


def _build_request_payload(args: argparse.Namespace, document: DocumentJob) -> dict[str, Any]:
    user_text = (
        f"Document title: {document.title or 'Unknown'}\n"
        f"Source URL: {document.source_url or 'Unknown'}\n"
        f"Chunk index: {document.chunk_index if document.chunk_index is not None else 'Unknown'}\n\n"
        f"Text:\n{document.raw_text}"
    )
    payload: dict[str, Any] = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0,
        "max_tokens": args.max_tokens,
    }
    if args.guided_json_mode in {"top-level", "both"}:
        payload["guided_json"] = EXTRACTION_SCHEMA
    if args.guided_json_mode in {"extra-body", "both"}:
        payload["extra_body"] = {"guided_json": EXTRACTION_SCHEMA}
    if args.response_format:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


async def _call_model(
    http_session: aiohttp.ClientSession,
    args: argparse.Namespace,
    document: DocumentJob,
) -> ExtractionResult:
    request_payload = _build_request_payload(args, document)
    try:
        async with http_session.post(args.model_url, json=request_payload, timeout=args.timeout_seconds) as response:
            body_text = await response.text()
            if response.status >= 400:
                return ExtractionResult(document, None, f"HTTP {response.status}: {body_text[:500]}")
            body = json.loads(body_text)
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
            parsed = _extract_json(content)
            if not isinstance(parsed, dict):
                return ExtractionResult(document, None, "model response was not a JSON object")
            return ExtractionResult(
                document=document,
                payload=parsed,
                error=None,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            )
    except Exception as exc:  # noqa: BLE001 - keep the bulk run moving and checkpoint the failure.
        return ExtractionResult(document, None, repr(exc))


def _entity_specs_from_result(result: ExtractionResult) -> dict[str, dict[str, Any]]:
    assert result.payload is not None
    specs: dict[str, dict[str, Any]] = {}

    def add_entity(name: Any, entity_type: Any, description: Any = None, evidence_text: Any = None) -> None:
        bounded_name = _bounded(name, 512)
        if not bounded_name:
            return
        bounded_type = _bounded(entity_type or "Unknown", 255) or "Unknown"
        normalized_name = normalize_graph_name(bounded_name)
        fact_key = build_graph_entity_fact_key(bounded_name, bounded_type, _bounded(evidence_text, 4096))
        specs[fact_key] = {
            "fact_key": fact_key,
            "entity_name": bounded_name,
            "normalized_name": _bounded(normalized_name, 512),
            "entity_type": bounded_type,
            "description": _bounded(description, 4096) or None,
            "evidence_text": _bounded(evidence_text, 4096) or None,
            "metadata_json": {"bulk_extractor": "local-vllm"},
        }

    entities = result.payload.get("entities") or []
    if isinstance(entities, list):
        for entity in entities:
            if isinstance(entity, dict):
                add_entity(
                    entity.get("name") or entity.get("entity_name"),
                    entity.get("type") or entity.get("entity_type"),
                    entity.get("description"),
                    entity.get("evidence_text"),
                )

    relationships = result.payload.get("relationships") or []
    if isinstance(relationships, list):
        for relationship in relationships:
            if not isinstance(relationship, dict):
                continue
            add_entity(
                relationship.get("source") or relationship.get("source_entity_name"),
                relationship.get("source_type") or relationship.get("source_entity_type") or "Unknown",
                evidence_text=relationship.get("exact_quote"),
            )
            add_entity(
                relationship.get("target") or relationship.get("target_entity_name"),
                relationship.get("target_type") or relationship.get("target_entity_type") or "Unknown",
                evidence_text=relationship.get("exact_quote"),
            )

    return specs


def _relationship_specs_from_result(
    result: ExtractionResult,
    entity_rows_by_name: dict[str, uuid.UUID],
    entity_rows_by_link: dict[str, uuid.UUID],
) -> list[dict[str, Any]]:
    assert result.payload is not None
    relationships = result.payload.get("relationships") or []
    specs: list[dict[str, Any]] = []
    if not isinstance(relationships, list):
        return specs

    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        source_name = _bounded(relationship.get("source") or relationship.get("source_entity_name"), 512)
        target_name = _bounded(relationship.get("target") or relationship.get("target_entity_name"), 512)
        relationship_type = _bounded(relationship.get("type") or relationship.get("relationship_type"), 255)
        exact_quote = str(relationship.get("exact_quote") or "").strip()
        if not source_name or not target_name or not relationship_type or not exact_quote:
            continue

        source_type = _bounded(relationship.get("source_type") or relationship.get("source_entity_type") or "Unknown", 255)
        target_type = _bounded(relationship.get("target_type") or relationship.get("target_entity_type") or "Unknown", 255)
        source_normalized = _bounded(normalize_graph_name(source_name), 512)
        target_normalized = _bounded(normalize_graph_name(target_name), 512)
        source_link = f"{source_normalized}::{normalize_graph_name(source_type)}"
        target_link = f"{target_normalized}::{normalize_graph_name(target_type)}"

        specs.append(
            {
                "fact_key": build_graph_relationship_fact_key(source_name, target_name, relationship_type, exact_quote),
                "source_entity_name": source_name,
                "source_entity_normalized_name": source_normalized,
                "source_entity_type": source_type,
                "target_entity_name": target_name,
                "target_entity_normalized_name": target_normalized,
                "target_entity_type": target_type,
                "relationship_type": relationship_type,
                "exact_quote": exact_quote,
                "source_entity_fact_id": entity_rows_by_link.get(source_link) or entity_rows_by_name.get(source_normalized),
                "target_entity_fact_id": entity_rows_by_link.get(target_link) or entity_rows_by_name.get(target_normalized),
                "metadata_json": {"bulk_extractor": "local-vllm"},
            }
        )
    return specs


async def _persist_result(
    result: ExtractionResult,
    *,
    site_id: str,
    run_id: str,
    task_frame_id: str,
    task_attempt_id: str,
) -> tuple[int, int]:
    if result.payload is None:
        return 0, 0

    run_uuid = uuid.UUID(run_id)
    site_uuid = uuid.UUID(site_id)
    document_uuid = uuid.UUID(result.document.document_id)
    task_uuid = uuid.UUID(task_frame_id)
    attempt_uuid = uuid.UUID(task_attempt_id)
    source_url = _bounded(result.document.source_url, 2048) or None
    entity_specs = _entity_specs_from_result(result)

    async with AsyncSessionLocal() as session:
        if entity_specs:
            entity_values = [
                {
                    "run_id": run_uuid,
                    "site_id": site_uuid,
                    "document_id": document_uuid,
                    "task_frame_id": task_uuid,
                    "task_attempt_id": attempt_uuid,
                    "fact_key": spec["fact_key"],
                    "entity_name": spec["entity_name"],
                    "normalized_name": spec["normalized_name"],
                    "entity_type": spec["entity_type"],
                    "description": spec["description"],
                    "evidence_text": spec["evidence_text"],
                    "source_url": source_url,
                    "metadata_json": spec["metadata_json"],
                }
                for spec in entity_specs.values()
            ]
            insert_stmt = pg_insert(GraphEntityFact).values(entity_values)
            await session.execute(insert_stmt.on_conflict_do_nothing(constraint="uq_graph_entity_facts_run_document_fact"))
            await session.flush()

        entity_rows_by_name: dict[str, uuid.UUID] = {}
        entity_rows_by_link: dict[str, uuid.UUID] = {}
        if entity_specs:
            entity_result = await session.execute(
                select(GraphEntityFact.id, GraphEntityFact.normalized_name, GraphEntityFact.entity_type).where(
                    GraphEntityFact.run_id == run_uuid,
                    GraphEntityFact.document_id == document_uuid,
                    GraphEntityFact.fact_key.in_(list(entity_specs.keys())),
                )
            )
            for entity_id, normalized_name, entity_type in entity_result.all():
                entity_rows_by_name[normalized_name] = entity_id
                entity_rows_by_link[f"{normalized_name}::{normalize_graph_name(entity_type)}"] = entity_id

        relationship_specs = _relationship_specs_from_result(result, entity_rows_by_name, entity_rows_by_link)
        if relationship_specs:
            relationship_values = [
                {
                    "run_id": run_uuid,
                    "site_id": site_uuid,
                    "document_id": document_uuid,
                    "task_frame_id": task_uuid,
                    "task_attempt_id": attempt_uuid,
                    "source_entity_fact_id": spec["source_entity_fact_id"],
                    "target_entity_fact_id": spec["target_entity_fact_id"],
                    "fact_key": spec["fact_key"],
                    "source_entity_name": spec["source_entity_name"],
                    "source_entity_normalized_name": spec["source_entity_normalized_name"],
                    "source_entity_type": spec["source_entity_type"],
                    "target_entity_name": spec["target_entity_name"],
                    "target_entity_normalized_name": spec["target_entity_normalized_name"],
                    "target_entity_type": spec["target_entity_type"],
                    "relationship_type": spec["relationship_type"],
                    "exact_quote": spec["exact_quote"],
                    "source_url": source_url,
                    "metadata_json": spec["metadata_json"],
                }
                for spec in relationship_specs
            ]
            insert_stmt = pg_insert(GraphRelationshipFact).values(relationship_values)
            await session.execute(
                insert_stmt.on_conflict_do_nothing(constraint="uq_graph_relationship_facts_run_document_fact")
            )

        await session.commit()
    return len(entity_specs), len(relationship_specs)


async def _check_model_server(args: argparse.Namespace) -> None:
    models_url = args.model_url.rsplit("/", 2)[0] + "/models"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(models_url, timeout=10) as response:
                text = await response.text()
                print(f"[model] {models_url} -> HTTP {response.status}: {text[:300]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[model] model server probe failed: {exc!r}")


async def run(args: argparse.Namespace) -> None:
    run_id, task_frame_id, task_attempt_id = await _ensure_bulk_run(
        args.site_id,
        args.run_id,
        args.reset_existing_run,
    )
    checkpoint_path = _checkpoint_path(run_id, args.checkpoint_file)
    processed_ids = _load_checkpoint(checkpoint_path)
    total_docs = await _count_documents(args.site_id)
    await _check_model_server(args)

    print("[bulk] site_id=", args.site_id)
    print("[bulk] run_id=", run_id)
    print("[bulk] task_frame_id=", task_frame_id)
    print("[bulk] task_attempt_id=", task_attempt_id)
    print("[bulk] checkpoint=", checkpoint_path)
    print(f"[bulk] corpus documents={total_docs:,}; checkpointed={len(processed_ids):,}")
    print(f"[bulk] workers={args.workers}; fetch_size={args.fetch_size}; model_url={args.model_url}")

    queue: asyncio.Queue[DocumentJob | None] = asyncio.Queue(maxsize=args.workers * args.queue_multiplier)
    persist_queue: asyncio.Queue[ExtractionResult | None] = asyncio.Queue(maxsize=args.workers * args.queue_multiplier)
    counters = {
        "submitted": 0,
        "processed": 0,
        "persisted": 0,
        "failed": 0,
        "entities": 0,
        "relationships": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    start_time = time.time()

    async def producer() -> None:
        async for batch in _document_batches(
            site_id=args.site_id,
            processed_ids=processed_ids,
            fetch_size=args.fetch_size,
            limit=args.limit,
        ):
            for document in batch:
                await queue.put(document)
                counters["submitted"] += 1
        for _ in range(args.workers):
            await queue.put(None)

    async def inference_worker(worker_id: int, http_session: aiohttp.ClientSession) -> None:
        while True:
            document = await queue.get()
            try:
                if document is None:
                    await persist_queue.put(None)
                    return
                result = await _call_model(http_session, args, document)
                counters["processed"] += 1
                counters["prompt_tokens"] += result.prompt_tokens
                counters["completion_tokens"] += result.completion_tokens
                if result.error:
                    counters["failed"] += 1
                await persist_queue.put(result)
            finally:
                queue.task_done()

    async def persistence_worker() -> None:
        finished_inference_workers = 0
        while finished_inference_workers < args.workers:
            result = await persist_queue.get()
            try:
                if result is None:
                    finished_inference_workers += 1
                    continue
                entity_count = 0
                relationship_count = 0
                if result.error is None:
                    entity_count, relationship_count = await _persist_result(
                        result,
                        site_id=args.site_id,
                        run_id=run_id,
                        task_frame_id=task_frame_id,
                        task_attempt_id=task_attempt_id,
                    )
                    counters["entities"] += entity_count
                    counters["relationships"] += relationship_count
                    counters["persisted"] += 1
                _append_checkpoint(checkpoint_path, result, entity_count, relationship_count)
            finally:
                persist_queue.task_done()

    async def reporter() -> None:
        while True:
            await asyncio.sleep(args.report_seconds)
            elapsed = max(time.time() - start_time, 1e-6)
            docs_per_min = counters["processed"] / elapsed * 60.0
            tokens = counters["prompt_tokens"] + counters["completion_tokens"]
            tokens_per_sec = tokens / elapsed
            print(
                "[bulk] "
                f"submitted={counters['submitted']:,} processed={counters['processed']:,} "
                f"persisted={counters['persisted']:,} failed={counters['failed']:,} "
                f"entities={counters['entities']:,} relationships={counters['relationships']:,} "
                f"docs/min={docs_per_min:,.1f} tokens/sec={tokens_per_sec:,.1f}"
            )

    connector = aiohttp.TCPConnector(limit=args.workers + 8, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=args.timeout_seconds + 30)
    reporter_task = asyncio.create_task(reporter())
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as http_session:
        tasks = [asyncio.create_task(producer())]
        tasks.extend(asyncio.create_task(inference_worker(i, http_session)) for i in range(args.workers))
        tasks.append(asyncio.create_task(persistence_worker()))
        await asyncio.gather(*tasks)
    reporter_task.cancel()
    try:
        await reporter_task
    except asyncio.CancelledError:
        pass

    elapsed = max(time.time() - start_time, 1e-6)
    async with AsyncSessionLocal() as session:
        task = await session.get(OrchestrationTaskFrameRecord, uuid.UUID(task_frame_id))
        attempt = await session.get(TaskAttempt, uuid.UUID(task_attempt_id))
        run_record = await session.get(PipelineRun, uuid.UUID(run_id))
        if task:
            task.status = "completed"
            task.outcome = "SUCCESS"
            task.completed_at = utcnow()
            task.lease_owner = None
        if attempt:
            attempt.status = "completed"
            attempt.outcome = "SUCCESS"
            attempt.finished_at = utcnow()
            attempt.output_json = dict(counters)
        if run_record:
            run_record.updated_at = utcnow()
        await session.commit()

    print(
        "[bulk] complete "
        f"run_id={run_id} processed={counters['processed']:,} failed={counters['failed']:,} "
        f"entities={counters['entities']:,} relationships={counters['relationships']:,} "
        f"elapsed={elapsed:,.1f}s"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk local graph extraction over the bespoke Postgres corpus.")
    parser.add_argument("--site-id", default=DEFAULT_SITE_ID)
    parser.add_argument("--run-id", default=None, help="Existing bulk run to resume. Omit to create a new run.")
    parser.add_argument("--reset-existing-run", action="store_true", help="Delete graph facts for --run-id before running.")
    parser.add_argument("--model-url", default=os.getenv("LOCAL_GRAPH_MODEL_URL", DEFAULT_MODEL_URL))
    parser.add_argument("--model", default=os.getenv("LOCAL_GRAPH_MODEL", DEFAULT_MODEL))
    parser.add_argument("--workers", type=int, default=int(os.getenv("LOCAL_GRAPH_WORKERS", "96")))
    parser.add_argument("--queue-multiplier", type=int, default=4)
    parser.add_argument("--fetch-size", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=1536)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--report-seconds", type=int, default=15)
    parser.add_argument("--checkpoint-file", default=None)
    parser.add_argument(
        "--guided-json-mode",
        choices=["top-level", "extra-body", "both", "none"],
        default=os.getenv("LOCAL_GRAPH_GUIDED_JSON_MODE", "top-level"),
    )
    parser.add_argument("--response-format", action="store_true", help="Also request JSON object response format.")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
