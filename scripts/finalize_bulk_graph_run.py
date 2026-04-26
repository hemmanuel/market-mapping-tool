#!/usr/bin/env python3
"""Finalize a bulk graph extraction run."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select


DEFAULT_SITE_ID = "d9f940ea-982c-4a04-8c6b-2d653457cf9a"
DEFAULT_POSTGRES_URL = "postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db"
DEFAULT_NEO4J_URI = "bolt://localhost:17687"

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("POSTGRES_URL", DEFAULT_POSTGRES_URL)
os.environ.setdefault("NEO4J_URI", DEFAULT_NEO4J_URI)
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "password")

from src.db.session import AsyncSessionLocal  # noqa: E402
from src.models.relational import Site  # noqa: E402
from src.orchestrator.core.graph_contracts import GraphProjectionInput  # noqa: E402
from src.orchestrator.core.graph_models import GraphEntityFact, GraphRelationshipFact  # noqa: E402
from src.orchestrator.core.ledger_models import (  # noqa: E402
    OrchestrationTaskFrameRecord,
    PipelineRun,
    TaskAttempt,
    utcnow,
)
from src.orchestrator.core.llm import BespokeLLMClient  # noqa: E402
from src.orchestrator.core.schemas import TaskFrame  # noqa: E402
from src.orchestrator.workers.canonical_persistence import PersistCanonicalEntitiesWorker  # noqa: E402
from src.orchestrator.workers.canonical_relationships import (  # noqa: E402
    CanonicalRelationshipAggregationWorker,
    PersistCanonicalRelationshipsWorker,
)
from src.orchestrator.workers.canonical_resolution import CanonicalEntityResolutionWorker  # noqa: E402
from src.orchestrator.workers.community_projection import (  # noqa: E402
    ProjectCommunitiesWorker,
    ProjectCommunitySummariesWorker,
)
from src.orchestrator.workers.graph_projection import (  # noqa: E402
    ProjectCanonicalEntitiesWorker,
    ProjectDocumentMentionsWorker,
    ProjectInteractsWithWorker,
    ProjectSemanticSimilarityWorker,
)
from src.orchestrator.workers.graph_publication import PruneGraphWorker, PublishGraphReadyWorker  # noqa: E402


def _compact_for_ledger(value: Any) -> Any:
    """Keep orchestration ledger JSON bounded for million-fact bulk runs."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, list):
        return {"count": len(value)}
    if isinstance(value, dict):
        return {key: _compact_for_ledger(item) for key, item in value.items()}
    return value


async def _ensure_stage_task(
    *,
    run_id: str,
    site_id: str,
    task_type: str,
    payload: dict[str, Any],
) -> tuple[TaskFrame, str]:
    run_uuid = uuid.UUID(run_id)
    site_uuid = uuid.UUID(site_id)
    async with AsyncSessionLocal() as session:
        run = await session.get(PipelineRun, run_uuid)
        if run is None:
            raise RuntimeError(f"Run {run_id} does not exist.")
        site = await session.get(Site, site_uuid)
        if site is None:
            raise RuntimeError(f"Site {site_id} does not exist.")

        result = await session.execute(
            select(OrchestrationTaskFrameRecord).where(
                OrchestrationTaskFrameRecord.run_id == run_uuid,
                OrchestrationTaskFrameRecord.task_type == task_type,
                OrchestrationTaskFrameRecord.idempotency_key == f"bulk-finalize:{task_type}",
            )
        )
        task_record = result.scalars().first()
        ledger_payload = _compact_for_ledger(payload)
        if task_record is None:
            task_record = OrchestrationTaskFrameRecord(
                run_id=run_uuid,
                site_id=site_uuid,
                task_type=task_type,
                payload_json=ledger_payload,
                priority=10,
                concurrency_class="bulk-finalize",
                idempotency_key=f"bulk-finalize:{task_type}",
                status="in_progress",
                started_at=utcnow(),
                lease_owner="bulk-finalize",
            )
            session.add(task_record)
            await session.flush()
        else:
            task_record.payload_json = ledger_payload
            task_record.status = "in_progress"
            task_record.outcome = None
            task_record.started_at = task_record.started_at or utcnow()
            task_record.completed_at = None
            task_record.lease_owner = "bulk-finalize"

        max_attempt_number = (
            await session.scalar(
                select(func.max(TaskAttempt.attempt_number)).where(TaskAttempt.task_frame_id == task_record.id)
            )
            or 0
        )
        attempt = TaskAttempt(
            task_frame_id=task_record.id,
            run_id=run_uuid,
            site_id=site_uuid,
            attempt_number=int(max_attempt_number) + 1,
            status="started",
            worker_version="bulk-finalize-v1",
            lease_owner="bulk-finalize",
        )
        session.add(attempt)
        await session.flush()
        await session.commit()

        task = TaskFrame(
            task_id=str(task_record.id),
            run_id=run_id,
            pipeline_id=site_id,
            task_type=task_type,
            payload=payload,
            status="in_progress",
            concurrency_class="bulk-finalize",
            idempotency_key=f"bulk-finalize:{task_type}",
        )
        return task, str(attempt.id)


async def _complete_stage(task_id: str, attempt_id: str, output: Any) -> None:
    output_json = _compact_for_ledger(output)
    async with AsyncSessionLocal() as session:
        task = await session.get(OrchestrationTaskFrameRecord, uuid.UUID(task_id))
        attempt = await session.get(TaskAttempt, uuid.UUID(attempt_id))
        if task:
            task.status = "completed"
            task.outcome = "SUCCESS"
            task.completed_at = utcnow()
            task.lease_owner = None
        if attempt:
            attempt.status = "completed"
            attempt.outcome = "SUCCESS"
            attempt.finished_at = utcnow()
            attempt.output_json = output_json
        await session.commit()


async def _fail_stage(task_id: str, attempt_id: str, exc: BaseException) -> None:
    async with AsyncSessionLocal() as session:
        task = await session.get(OrchestrationTaskFrameRecord, uuid.UUID(task_id))
        attempt = await session.get(TaskAttempt, uuid.UUID(attempt_id))
        if task:
            task.status = "dead_lettered"
            task.outcome = "FAILED"
            task.completed_at = utcnow()
            task.last_error_code = exc.__class__.__name__
            task.last_error_payload = {"message": str(exc)}
            task.lease_owner = None
        if attempt:
            attempt.status = "failed"
            attempt.outcome = "FAILED"
            attempt.finished_at = utcnow()
            attempt.error_code = exc.__class__.__name__
            attempt.error_payload = {"message": str(exc)}
        await session.commit()


async def _run_stage(
    *,
    run_id: str,
    site_id: str,
    task_type: str,
    payload: dict[str, Any],
    worker: Any,
    accepts_attempt_id: bool = False,
) -> Any:
    print(f"[finalize] starting {task_type}")
    task, attempt_id = await _ensure_stage_task(run_id=run_id, site_id=site_id, task_type=task_type, payload=payload)
    try:
        if accepts_attempt_id:
            output = await worker.execute(task, attempt_id)
        else:
            output = await worker.execute(task)
    except Exception as exc:  # noqa: BLE001 - operational script records stage failure.
        await _fail_stage(task.task_id, attempt_id, exc)
        raise
    await _complete_stage(task.task_id, attempt_id, output)
    print(f"[finalize] completed {task_type}: {_compact_for_ledger(output)}")
    return output


async def _graph_fact_counts(run_id: str, site_id: str) -> tuple[int, int, int]:
    run_uuid = uuid.UUID(run_id)
    site_uuid = uuid.UUID(site_id)
    async with AsyncSessionLocal() as session:
        entity_count = int(
            await session.scalar(
                select(func.count())
                .select_from(GraphEntityFact)
                .where(GraphEntityFact.run_id == run_uuid, GraphEntityFact.site_id == site_uuid)
            )
            or 0
        )
        relationship_count = int(
            await session.scalar(
                select(func.count())
                .select_from(GraphRelationshipFact)
                .where(GraphRelationshipFact.run_id == run_uuid, GraphRelationshipFact.site_id == site_uuid)
            )
            or 0
        )
        document_count = int(
            await session.scalar(
                select(func.count(func.distinct(GraphEntityFact.document_id))).where(
                    GraphEntityFact.run_id == run_uuid,
                    GraphEntityFact.site_id == site_uuid,
                )
            )
            or 0
        )
    return entity_count, relationship_count, document_count


async def run(args: argparse.Namespace) -> None:
    entity_count, relationship_count, document_count = await _graph_fact_counts(args.run_id, args.site_id)
    print(
        "[finalize] input facts "
        f"entities={entity_count:,} relationships={relationship_count:,} documents={document_count:,}"
    )
    if entity_count == 0:
        raise RuntimeError("No graph entity facts exist for this run. Run bulk_local_graph_extract.py first.")

    if args.skip_canonical_entities:
        print("[finalize] skipping canonical entity resolution/persistence")
    else:
        resolution_output = await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="CANONICAL_ENTITY_RESOLUTION",
            payload={"site_id": args.site_id, "run_id": args.run_id, "documents": []},
            worker=CanonicalEntityResolutionWorker(),
        )
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PERSIST_CANONICAL_ENTITIES",
            payload={
                "site_id": args.site_id,
                "run_id": args.run_id,
                "documents": [],
                "canonical_entities": [item.model_dump() for item in resolution_output.canonical_entities],
                "memberships": [item.model_dump() for item in resolution_output.memberships],
            },
            worker=PersistCanonicalEntitiesWorker(),
            accepts_attempt_id=True,
        )

    if args.skip_canonical_relationships:
        print("[finalize] skipping canonical relationship aggregation/persistence")
    else:
        relationship_output = await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="CANONICAL_RELATIONSHIP_AGGREGATION",
            payload={"site_id": args.site_id, "run_id": args.run_id, "documents": []},
            worker=CanonicalRelationshipAggregationWorker(),
        )
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PERSIST_CANONICAL_RELATIONSHIPS",
            payload={
                "site_id": args.site_id,
                "run_id": args.run_id,
                "documents": [],
                "relationships": [item.model_dump() for item in relationship_output.relationships],
            },
            worker=PersistCanonicalRelationshipsWorker(),
            accepts_attempt_id=True,
        )

    projection_payload = GraphProjectionInput(site_id=args.site_id, run_id=args.run_id).model_dump()
    if args.skip_core_projection:
        print("[finalize] skipping canonical entity/document/relationship projection")
    else:
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PROJECT_CANONICAL_ENTITIES",
            payload=projection_payload,
            worker=ProjectCanonicalEntitiesWorker(),
        )
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PROJECT_DOCUMENT_MENTIONS",
            payload=projection_payload,
            worker=ProjectDocumentMentionsWorker(),
        )
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PROJECT_INTERACTS_WITH",
            payload=projection_payload,
            worker=ProjectInteractsWithWorker(),
        )

    if args.semantic_similarity:
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PROJECT_SEMANTIC_SIMILARITY",
            payload=projection_payload,
            worker=ProjectSemanticSimilarityWorker(),
        )

    await _run_stage(
        run_id=args.run_id,
        site_id=args.site_id,
        task_type="PROJECT_COMMUNITIES",
        payload=projection_payload,
        worker=ProjectCommunitiesWorker(),
        accepts_attempt_id=True,
    )

    if args.summarize_communities:
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PROJECT_COMMUNITY_SUMMARIES",
            payload=projection_payload,
            worker=ProjectCommunitySummariesWorker(BespokeLLMClient()),
            accepts_attempt_id=True,
        )

    if args.prune:
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PRUNE_GRAPH",
            payload=projection_payload,
            worker=PruneGraphWorker(),
        )

    if args.publish_ready:
        if not args.semantic_similarity:
            raise RuntimeError("--publish-ready requires --semantic-similarity so verification has a similarity metric.")
        await _run_stage(
            run_id=args.run_id,
            site_id=args.site_id,
            task_type="PUBLISH_GRAPH_READY",
            payload=projection_payload,
            worker=PublishGraphReadyWorker(),
        )

    if args.mark_run_completed:
        async with AsyncSessionLocal() as session:
            run_record = await session.get(PipelineRun, uuid.UUID(args.run_id))
            if run_record:
                run_record.status = "completed"
                run_record.completed_at = utcnow()
                run_record.updated_at = utcnow()
                await session.commit()

    print("[finalize] done")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize a bulk graph extraction run into canonical/projected graph state.")
    parser.add_argument("--site-id", default=DEFAULT_SITE_ID)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--semantic-similarity", action="store_true", help="Project SIMILAR_TO edges. Can be expensive.")
    parser.add_argument("--summarize-communities", action="store_true", help="Use LLM calls to name/summarize communities.")
    parser.add_argument("--no-prune", dest="prune", action="store_false", help="Do not prune older Neo4j projection state.")
    parser.add_argument("--publish-ready", action="store_true", help="Verify graph counts and mark the site ready.")
    parser.add_argument("--mark-run-completed", action="store_true", help="Mark the pipeline run completed at the end.")
    parser.add_argument(
        "--skip-canonical-entities",
        action="store_true",
        help="Resume after canonical entity resolution and persistence have already completed.",
    )
    parser.add_argument(
        "--skip-canonical-relationships",
        action="store_true",
        help="Resume after canonical relationship aggregation and persistence have already completed.",
    )
    parser.add_argument(
        "--skip-core-projection",
        action="store_true",
        help="Resume after canonical entities, document mentions, and relationship edges have already been projected.",
    )
    parser.set_defaults(prune=True)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
