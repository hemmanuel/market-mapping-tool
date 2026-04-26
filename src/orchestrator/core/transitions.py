from dataclasses import dataclass, field
from datetime import timedelta
import uuid
from typing import Any, Dict, Iterable, Optional

from src.orchestrator.core.ledger import utcnow
from src.orchestrator.core.schemas import TaskFrame


TERMINAL_NOOP = "noop"
TERMINAL_FAIL_RUN = "fail_run"


@dataclass(frozen=True)
class TaskEmission:
    task_type: str
    payload: Dict[str, Any]
    fan_out: Optional[str] = None
    delay_seconds: int = 0
    priority: int = 100
    max_retries: int = 3
    concurrency_class: Optional[str] = None
    dedupe_key: Optional[str] = None
    idempotency_key: Optional[str] = None
    partition_key: Optional[str] = None


@dataclass(frozen=True)
class TransitionRoute:
    emits: list[TaskEmission] = field(default_factory=list)
    terminal_action: Optional[str] = None


@dataclass(frozen=True)
class TransitionSpec:
    task_type: str
    routes: Dict[str, TransitionRoute]


def _coerce_object(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _resolve_path(root: Any, path_parts: Iterable[str]) -> Any:
    current = _coerce_object(root)
    for part in path_parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        current = _coerce_object(current)
    return current


def resolve_reference(
    value: Any,
    *,
    context: dict[str, Any],
    task: TaskFrame,
    output: dict[str, Any],
    item: Any = None,
) -> Any:
    if not isinstance(value, str) or not value.startswith("$"):
        return value

    expression = value[1:]
    if expression == "item":
        return _coerce_object(item)

    root_name, *path_parts = expression.split(".")
    roots = {
        "context": context,
        "task": task.model_dump(),
        "output": output,
        "item": _coerce_object(item),
    }
    return _resolve_path(roots.get(root_name), path_parts)


def materialize_route(
    route: TransitionRoute,
    *,
    run_id: str,
    pipeline_id: str,
    context: dict[str, Any],
    task: TaskFrame,
    output: dict[str, Any],
) -> list[TaskFrame]:
    materialized: list[TaskFrame] = []
    for emission in route.emits:
        emitted_items = [None]
        if emission.fan_out:
            resolved = resolve_reference(
                emission.fan_out,
                context=context,
                task=task,
                output=output,
            )
            if not resolved:
                continue
            if isinstance(resolved, (list, tuple, set)):
                emitted_items = list(resolved)
            else:
                emitted_items = [resolved]

        for item in emitted_items:
            payload = {
                key: resolve_reference(
                    mapping,
                    context=context,
                    task=task,
                    output=output,
                    item=item,
                )
                for key, mapping in emission.payload.items()
            }
            available_at = None
            scheduled_at = None
            if emission.delay_seconds > 0:
                scheduled_at = utcnow()
                available_at = scheduled_at + timedelta(seconds=emission.delay_seconds)

            materialized.append(
                TaskFrame(
                    task_id=str(uuid.uuid4()),
                    run_id=run_id,
                    pipeline_id=pipeline_id,
                    parent_task_id=task.task_id,
                    root_task_id=task.root_task_id or task.task_id,
                    task_type=emission.task_type,
                    payload=payload,
                    status="pending",
                    scheduled_at=scheduled_at,
                    available_at=available_at,
                    priority=emission.priority,
                    max_retries=emission.max_retries,
                    concurrency_class=emission.concurrency_class,
                    dedupe_key=_stringify_optional(
                        resolve_reference(
                            emission.dedupe_key,
                            context=context,
                            task=task,
                            output=output,
                            item=item,
                        )
                    ),
                    idempotency_key=_stringify_optional(
                        resolve_reference(
                            emission.idempotency_key,
                            context=context,
                            task=task,
                            output=output,
                            item=item,
                        )
                    ),
                    partition_key=_stringify_optional(
                        resolve_reference(
                            emission.partition_key,
                            context=context,
                            task=task,
                            output=output,
                            item=item,
                        )
                    ),
                )
            )
    return materialized


def _stringify_optional(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


TRANSITION_MODEL: dict[str, TransitionSpec] = {
    "MARKET_SIZING": TransitionSpec(
        task_type="MARKET_SIZING",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="EXTRACT_COMPANIES",
                        fan_out="$output.micro_buckets",
                        payload={
                            "niche": "$context.niche",
                            "micro_bucket": "$item",
                        },
                        priority=300,
                        concurrency_class="llm",
                        idempotency_key="$item",
                        partition_key="$context.niche",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "EXTRACT_COMPANIES": TransitionSpec(
        task_type="EXTRACT_COMPANIES",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="ENRICH_COMPANY",
                        fan_out="$output.companies",
                        payload={
                            "niche": "$context.niche",
                            "company_name": "$item",
                            "poll_count": 0,
                        },
                        priority=150,
                        concurrency_class="llm",
                        idempotency_key="$item",
                        partition_key="$item",
                    ),
                    TaskEmission(
                        task_type="PLAN_COMPANY_SEARCH",
                        fan_out="$output.companies",
                        payload={
                            "niche": "$context.niche",
                            "company_name": "$item",
                        },
                        priority=200,
                        concurrency_class="llm",
                        idempotency_key="$item",
                        partition_key="$item",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "ENRICH_COMPANY": TransitionSpec(
        task_type="ENRICH_COMPANY",
        routes={
            "WAITING": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="ENRICH_COMPANY",
                        delay_seconds=5,
                        payload={
                            "niche": "$task.payload.niche",
                            "company_name": "$task.payload.company_name",
                            "poll_count": "$output.poll_count",
                        },
                        priority=150,
                        concurrency_class="llm",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PERSIST_COMPANY_ENRICHMENT",
                        payload={
                            "niche": "$task.payload.niche",
                            "company_name": "$task.payload.company_name",
                            "company_profile": "$output.company_profile",
                            "source_document_ids": "$output.source_document_ids",
                            "source_urls": "$output.source_urls",
                        },
                        priority=55,
                        concurrency_class="storage",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "NO_EVIDENCE": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "PLAN_COMPANY_SEARCH": TransitionSpec(
        task_type="PLAN_COMPANY_SEARCH",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="SEARCH_QUERY",
                        fan_out="$output.search_queries",
                        payload={
                            "niche": "$context.niche",
                            "company_name": "$task.payload.company_name",
                            "query": "$item.query",
                            "target_domains": "$item.target_domains",
                        },
                        priority=100,
                        concurrency_class="search",
                        idempotency_key="$item.query",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "SEARCH_QUERY": TransitionSpec(
        task_type="SEARCH_QUERY",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="GLOBAL_DEDUP_URL",
                        fan_out="$output.urls",
                        payload={
                            "url": "$item",
                            "niche": "$context.niche",
                            "company_name": "$task.payload.company_name",
                            "schema_entities": "$context.schema_entities",
                        },
                        priority=90,
                        concurrency_class="storage",
                        idempotency_key="$item",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "GLOBAL_DEDUP_URL": TransitionSpec(
        task_type="GLOBAL_DEDUP_URL",
        routes={
            "SCRAPE_REQUIRED": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="SCRAPE_URL",
                        payload={
                            "url": "$task.payload.url",
                            "niche": "$task.payload.niche",
                            "company_name": "$task.payload.company_name",
                            "schema_entities": "$task.payload.schema_entities",
                        },
                        priority=80,
                        concurrency_class="scrape",
                        idempotency_key="$task.payload.url",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "CACHE_HIT": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "SCRAPE_URL": TransitionSpec(
        task_type="SCRAPE_URL",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="BOUNCER_EVALUATION",
                        payload={
                            "raw_text": "$output.raw_text",
                            "url": "$task.payload.url",
                            "niche": "$task.payload.niche",
                            "schema_entities": "$task.payload.schema_entities",
                            "company_name": "$task.payload.company_name",
                            "storage_object": "$output.storage_object",
                        },
                        priority=70,
                        concurrency_class="cpu",
                        idempotency_key="$task.payload.url",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "EMPTY": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "BOUNCER_EVALUATION": TransitionSpec(
        task_type="BOUNCER_EVALUATION",
        routes={
            "IS_RELEVANT": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="VECTOR_STORAGE",
                        payload={
                            "raw_text": "$task.payload.raw_text",
                            "url": "$task.payload.url",
                            "storage_object": "$task.payload.storage_object",
                            "company_name": "$task.payload.company_name",
                        },
                        priority=60,
                        concurrency_class="embedding",
                        idempotency_key="$task.payload.url",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "NOT_RELEVANT": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "VECTOR_STORAGE": TransitionSpec(
        task_type="VECTOR_STORAGE",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="GRAPH_DOCUMENT_SELECTION",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "candidate_document_ids": "$output.document_ids",
                        },
                        priority=50,
                        concurrency_class="storage",
                        idempotency_key="$task.payload.url",
                        partition_key="$task.payload.url",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "PERSIST_COMPANY_ENRICHMENT": TransitionSpec(
        task_type="PERSIST_COMPANY_ENRICHMENT",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PROJECT_COMPANY_ENRICHMENT",
                        payload={
                            "company_enrichment_id": "$output.company_enrichment_id",
                        },
                        priority=54,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.company_name",
                    )
                ]
            ),
            "SKIPPED": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "PROJECT_COMPANY_ENRICHMENT": TransitionSpec(
        task_type="PROJECT_COMPANY_ENRICHMENT",
        routes={
            "SUCCESS": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "GRAPH_DOCUMENT_SELECTION": TransitionSpec(
        task_type="GRAPH_DOCUMENT_SELECTION",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="GRAPH_FACT_EXTRACTION",
                        fan_out="$output.documents",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "niche": "$context.niche",
                            "schema_entities": "$context.schema_entities",
                            "schema_relationships": "$context.schema_relationships",
                            "document": "$item",
                        },
                        priority=40,
                        concurrency_class="llm",
                        idempotency_key="$item.document_id",
                        partition_key="$item.source_url",
                    ),
                    TaskEmission(
                        task_type="GRAPH_EXTRACTION_BARRIER",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "selection_task_id": "$task.task_id",
                            "documents": "$output.documents",
                            "poll_count": 0,
                        },
                        priority=45,
                        concurrency_class="storage",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "GRAPH_EXTRACTION_BARRIER": TransitionSpec(
        task_type="GRAPH_EXTRACTION_BARRIER",
        routes={
            "WAITING": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="GRAPH_EXTRACTION_BARRIER",
                        delay_seconds=2,
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "selection_task_id": "$task.payload.selection_task_id",
                            "documents": "$task.payload.documents",
                            "poll_count": "$output.poll_count",
                        },
                        priority=45,
                        concurrency_class="storage",
                    )
                ]
            ),
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="CANONICAL_ENTITY_RESOLUTION",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "selection_task_id": "$task.payload.selection_task_id",
                            "documents": "$task.payload.documents",
                        },
                        priority=35,
                        concurrency_class="graph_resolution",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "GRAPH_FACT_EXTRACTION": TransitionSpec(
        task_type="GRAPH_FACT_EXTRACTION",
        routes={
            "SUCCESS": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_NOOP),
        },
    ),
    "CANONICAL_ENTITY_RESOLUTION": TransitionSpec(
        task_type="CANONICAL_ENTITY_RESOLUTION",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PERSIST_CANONICAL_ENTITIES",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "selection_task_id": "$task.payload.selection_task_id",
                            "documents": "$task.payload.documents",
                            "canonical_entities": "$output.canonical_entities",
                            "memberships": "$output.memberships",
                        },
                        priority=30,
                        concurrency_class="graph_resolution",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PERSIST_CANONICAL_ENTITIES": TransitionSpec(
        task_type="PERSIST_CANONICAL_ENTITIES",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="CANONICAL_RELATIONSHIP_AGGREGATION",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "selection_task_id": "$task.payload.selection_task_id",
                            "documents": "$task.payload.documents",
                        },
                        priority=28,
                        concurrency_class="graph_resolution",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "CANONICAL_RELATIONSHIP_AGGREGATION": TransitionSpec(
        task_type="CANONICAL_RELATIONSHIP_AGGREGATION",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PERSIST_CANONICAL_RELATIONSHIPS",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                            "selection_task_id": "$task.payload.selection_task_id",
                            "documents": "$task.payload.documents",
                            "relationships": "$output.relationships",
                        },
                        priority=27,
                        concurrency_class="graph_resolution",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PERSIST_CANONICAL_RELATIONSHIPS": TransitionSpec(
        task_type="PERSIST_CANONICAL_RELATIONSHIPS",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PROJECT_CANONICAL_ENTITIES",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=25,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PROJECT_CANONICAL_ENTITIES": TransitionSpec(
        task_type="PROJECT_CANONICAL_ENTITIES",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PROJECT_DOCUMENT_MENTIONS",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=20,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PROJECT_DOCUMENT_MENTIONS": TransitionSpec(
        task_type="PROJECT_DOCUMENT_MENTIONS",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PROJECT_INTERACTS_WITH",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=19,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PROJECT_INTERACTS_WITH": TransitionSpec(
        task_type="PROJECT_INTERACTS_WITH",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PROJECT_SEMANTIC_SIMILARITY",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=18,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PROJECT_SEMANTIC_SIMILARITY": TransitionSpec(
        task_type="PROJECT_SEMANTIC_SIMILARITY",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PROJECT_COMMUNITIES",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=17,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PROJECT_COMMUNITIES": TransitionSpec(
        task_type="PROJECT_COMMUNITIES",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PROJECT_COMMUNITY_SUMMARIES",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=16,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PROJECT_COMMUNITY_SUMMARIES": TransitionSpec(
        task_type="PROJECT_COMMUNITY_SUMMARIES",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PRUNE_GRAPH",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=15,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PRUNE_GRAPH": TransitionSpec(
        task_type="PRUNE_GRAPH",
        routes={
            "SUCCESS": TransitionRoute(
                emits=[
                    TaskEmission(
                        task_type="PUBLISH_GRAPH_READY",
                        payload={
                            "site_id": "$task.pipeline_id",
                            "run_id": "$task.run_id",
                        },
                        priority=14,
                        concurrency_class="graph_projection",
                        partition_key="$task.payload.site_id",
                    )
                ]
            ),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
    "PUBLISH_GRAPH_READY": TransitionSpec(
        task_type="PUBLISH_GRAPH_READY",
        routes={
            "SUCCESS": TransitionRoute(terminal_action=TERMINAL_NOOP),
            "FAILED": TransitionRoute(terminal_action=TERMINAL_FAIL_RUN),
        },
    ),
}
