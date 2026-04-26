import uuid

from sqlalchemy import select

from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.orchestrator.core.graph_contracts import (
    CanonicalEntityMembershipSpec,
    CanonicalEntityResolutionOutput,
    CanonicalEntityResolutionTaskInput,
    CanonicalEntitySpec,
)
from src.orchestrator.core.graph_models import GraphEntityFact
from src.orchestrator.core.graph_normalization import (
    choose_canonical_name,
    normalize_entity_name_for_resolution,
    normalize_entity_type,
)
from src.orchestrator.core.graph_store import build_canonical_entity_key, normalize_graph_name
from src.orchestrator.core.schemas import TaskFrame


class CanonicalEntityResolutionWorker:
    async def execute(self, task: TaskFrame) -> CanonicalEntityResolutionOutput:
        payload = CanonicalEntityResolutionTaskInput(**task.payload)
        pipeline_id = task.pipeline_id
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GraphEntityFact).where(
                    GraphEntityFact.run_id == run_uuid,
                    GraphEntityFact.site_id == site_uuid,
                )
            )
            entity_facts = result.scalars().all()

        if not entity_facts:
            await event_manager.publish(
                pipeline_id,
                {"type": "log", "message": "[CanonicalResolution] No graph entity facts available yet."},
            )
            return CanonicalEntityResolutionOutput(canonical_entities=[], memberships=[])

        groups: dict[tuple[str, str], list[GraphEntityFact]] = {}
        for fact in entity_facts:
            normalized_type = normalize_entity_type(fact.entity_type, fact.entity_name, fact.description)
            resolution_name = normalize_entity_name_for_resolution(fact.entity_name)
            if not resolution_name:
                resolution_name = fact.normalized_name or normalize_graph_name(fact.entity_name)
            group_key = (normalized_type, resolution_name)
            groups.setdefault(group_key, []).append(fact)

        canonical_entities: list[CanonicalEntitySpec] = []
        memberships: list[CanonicalEntityMembershipSpec] = []
        for (entity_type, normalized_name), facts in groups.items():
            aliases = sorted({fact.entity_name for fact in facts if fact.entity_name}, key=lambda value: (len(value), value.lower()))
            canonical_name = choose_canonical_name(aliases)
            canonical_key = build_canonical_entity_key(normalized_name or canonical_name, entity_type)
            descriptions = [fact.description for fact in facts if fact.description]
            description = max(descriptions, key=len) if descriptions else None
            raw_types = sorted({fact.entity_type for fact in facts if fact.entity_type})
            resolution_confidence = 1.0 if len(aliases) <= 1 and len(raw_types) <= 1 else 0.88

            canonical_entities.append(
                CanonicalEntitySpec(
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                    canonical_key=canonical_key,
                    normalized_name=normalized_name or normalize_graph_name(canonical_name),
                    description=description,
                    aliases=aliases,
                    resolution_confidence=resolution_confidence,
                    metadata={
                        "fact_count": len(facts),
                        "raw_entity_types": raw_types,
                        "resolution_name": normalized_name,
                        "resolution_strategy": "type_normalized_alias_key",
                    },
                )
            )

            for fact in facts:
                memberships.append(
                    CanonicalEntityMembershipSpec(
                        graph_entity_fact_id=str(fact.id),
                        canonical_name=canonical_name,
                        entity_type=entity_type,
                        canonical_key=canonical_key,
                        resolution_reason="normalized_name_exact_match",
                        confidence=resolution_confidence,
                        metadata={
                            "source_url": fact.source_url,
                            "entity_name": fact.entity_name,
                            "raw_entity_type": fact.entity_type,
                            "normalized_entity_type": entity_type,
                            "resolution_name": normalized_name,
                        },
                    )
                )

        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": (
                    f"[CanonicalResolution] Resolved {len(entity_facts)} entity fact(s) into "
                    f"{len(canonical_entities)} canonical entity group(s) using type-normalized alias keys."
                ),
            },
        )
        return CanonicalEntityResolutionOutput(
            canonical_entities=canonical_entities,
            memberships=memberships,
        )
