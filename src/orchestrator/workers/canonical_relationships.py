import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import aliased

from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.orchestrator.core.graph_contracts import (
    CanonicalRelationshipAggregationInput,
    CanonicalRelationshipAggregationOutput,
    CanonicalRelationshipSpec,
    PersistCanonicalRelationshipsInput,
    PersistCanonicalRelationshipsResult,
)
from src.orchestrator.core.graph_models import (
    CanonicalEntityMembership,
    CanonicalGraphEntity,
    GraphRelationshipFact,
)
from src.orchestrator.core.graph_normalization import normalize_relationship_type
from src.orchestrator.core.graph_store import (
    build_canonical_relationship_key,
    persist_canonical_relationships,
)
from src.orchestrator.core.schemas import TaskFrame


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class CanonicalRelationshipAggregationWorker:
    async def execute(self, task: TaskFrame) -> CanonicalRelationshipAggregationOutput:
        payload = CanonicalRelationshipAggregationInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)
        pipeline_id = task.pipeline_id

        source_membership = aliased(CanonicalEntityMembership)
        target_membership = aliased(CanonicalEntityMembership)
        source_canonical = aliased(CanonicalGraphEntity)
        target_canonical = aliased(CanonicalGraphEntity)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    GraphRelationshipFact.id,
                    GraphRelationshipFact.relationship_type,
                    GraphRelationshipFact.exact_quote,
                    GraphRelationshipFact.source_url,
                    source_canonical.canonical_key,
                    target_canonical.canonical_key,
                )
                .join(source_membership, source_membership.graph_entity_fact_id == GraphRelationshipFact.source_entity_fact_id)
                .join(target_membership, target_membership.graph_entity_fact_id == GraphRelationshipFact.target_entity_fact_id)
                .join(source_canonical, source_canonical.id == source_membership.canonical_entity_id)
                .join(target_canonical, target_canonical.id == target_membership.canonical_entity_id)
                .where(
                    GraphRelationshipFact.run_id == run_uuid,
                    GraphRelationshipFact.site_id == site_uuid,
                    source_membership.run_id == run_uuid,
                    target_membership.run_id == run_uuid,
                    source_canonical.run_id == run_uuid,
                    target_canonical.run_id == run_uuid,
                    source_canonical.status == "active",
                    target_canonical.status == "active",
                )
            )
            rows = result.all()

        grouped: dict[tuple[str, str, str], dict] = defaultdict(
            lambda: {
                "quotes": [],
                "raw_relationship_types": [],
                "source_urls": [],
                "supporting_fact_ids": [],
            }
        )
        skipped_self_loops = 0
        for fact_id, relationship_type, exact_quote, source_url, source_canonical_key, target_canonical_key in rows:
            if source_canonical_key == target_canonical_key:
                skipped_self_loops += 1
                continue

            normalized_relationship_type = normalize_relationship_type(relationship_type, exact_quote)
            group_key = (source_canonical_key, target_canonical_key, normalized_relationship_type)
            grouped[group_key]["quotes"].append(exact_quote)
            grouped[group_key]["raw_relationship_types"].append(relationship_type)
            if source_url:
                grouped[group_key]["source_urls"].append(source_url)
            grouped[group_key]["supporting_fact_ids"].append(str(fact_id))

        relationships: list[CanonicalRelationshipSpec] = []
        for (source_canonical_key, target_canonical_key, relationship_type), aggregate in grouped.items():
            quotes = _unique_strings(aggregate["quotes"])
            source_urls = _unique_strings(aggregate["source_urls"])
            raw_relationship_types = _unique_strings(aggregate["raw_relationship_types"])
            supporting_fact_ids = _unique_strings(aggregate["supporting_fact_ids"])
            evidence_count = len(supporting_fact_ids)
            weight = float(evidence_count + (len(source_urls) * 0.5))
            canonical_relationship_key = build_canonical_relationship_key(
                source_canonical_key,
                target_canonical_key,
                relationship_type,
            )
            relationships.append(
                CanonicalRelationshipSpec(
                    source_canonical_key=source_canonical_key,
                    target_canonical_key=target_canonical_key,
                    relationship_type=relationship_type,
                    canonical_relationship_key=canonical_relationship_key,
                    normalized_relationship_type=relationship_type,
                    evidence_count=evidence_count,
                    weight=weight,
                    quotes=quotes,
                    source_urls=source_urls,
                    supporting_fact_ids=supporting_fact_ids,
                    metadata={
                        "aggregation_strategy": "canonical_endpoint_normalized_relationship_type",
                        "raw_relationship_types": raw_relationship_types,
                        "skipped_self_loops": skipped_self_loops,
                    },
                )
            )

        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": (
                    f"[CanonicalRelationshipAggregation] Aggregated {len(rows)} raw relationship fact(s) into "
                    f"{len(relationships)} canonical relationship(s)."
                ),
            },
        )
        return CanonicalRelationshipAggregationOutput(relationships=relationships)


class PersistCanonicalRelationshipsWorker:
    accepts_attempt_id = True

    async def execute(self, task: TaskFrame, attempt_id: str | None = None) -> PersistCanonicalRelationshipsResult:
        if not attempt_id:
            raise RuntimeError("PersistCanonicalRelationshipsWorker requires a task attempt id for durable lineage.")

        payload = PersistCanonicalRelationshipsInput(**task.payload)
        output = CanonicalRelationshipAggregationOutput(relationships=payload.relationships)

        async with AsyncSessionLocal() as session:
            persisted = await persist_canonical_relationships(
                session,
                run_id=payload.run_id,
                site_id=payload.site_id,
                task_frame_id=task.task_id,
                task_attempt_id=attempt_id,
                output=output,
            )
            await session.commit()

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    "[CanonicalRelationshipPersistence] Persisted "
                    f"{len(persisted.canonical_relationship_ids)} canonical relationship(s)."
                ),
            },
        )
        return persisted
