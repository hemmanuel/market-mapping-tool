import hashlib
import re
import uuid
from typing import Dict, Iterable, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.orchestrator.core.graph_contracts import (
    CanonicalCommunitySpec,
    CanonicalRelationshipAggregationOutput,
    CommunitySummarySpec,
    CanonicalEntityResolutionOutput,
    GraphFactExtractionOutput,
    PersistCanonicalCommunitiesResult,
    PersistCanonicalEntitiesResult,
    PersistCanonicalRelationshipsResult,
    PersistGraphFactsResult,
)
from src.orchestrator.core.graph_models import (
    CanonicalCommunityMembership,
    CanonicalEntityMembership,
    CanonicalGraphCommunity,
    CanonicalGraphEntity,
    CanonicalGraphRelationship,
    GraphEntityFact,
    GraphRelationshipFact,
)


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_graph_name(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value.strip().lower())


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _stable_hash(parts: Sequence[str]) -> str:
    joined = "::".join(part for part in parts if part)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def build_graph_entity_fact_key(entity_name: str, entity_type: str, evidence_text: str | None = None) -> str:
    return _stable_hash(
        [
            normalize_graph_name(entity_name),
            normalize_graph_name(entity_type),
            normalize_graph_name(evidence_text),
        ]
    )


def build_graph_relationship_fact_key(
    source_entity_name: str,
    target_entity_name: str,
    relationship_type: str,
    exact_quote: str,
) -> str:
    return _stable_hash(
        [
            normalize_graph_name(source_entity_name),
            normalize_graph_name(target_entity_name),
            normalize_graph_name(relationship_type),
            normalize_graph_name(exact_quote),
        ]
    )


def build_canonical_entity_key(canonical_name: str, entity_type: str) -> str:
    return _stable_hash([normalize_graph_name(canonical_name), normalize_graph_name(entity_type)])


def build_canonical_relationship_key(
    source_canonical_key: str,
    target_canonical_key: str,
    relationship_type: str,
) -> str:
    return _stable_hash(
        [
            normalize_graph_name(source_canonical_key),
            normalize_graph_name(target_canonical_key),
            normalize_graph_name(relationship_type),
        ]
    )


def build_canonical_community_key(member_canonical_keys: Sequence[str], algorithm: str = "louvain") -> str:
    unique_keys = sorted({normalize_graph_name(key) for key in member_canonical_keys if key})
    return _stable_hash([normalize_graph_name(algorithm), *unique_keys])


def _prefer_longer(existing: str | None, incoming: str | None) -> str | None:
    if not existing:
        return incoming
    if not incoming:
        return existing
    return incoming if len(incoming) > len(existing) else existing


def _merge_dicts(existing: dict | None, incoming: dict | None) -> dict:
    merged = dict(existing or {})
    merged.update(incoming or {})
    return merged


def _unique_strings(values: Iterable[str]) -> list[str]:
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


def _batches(values: Sequence, batch_size: int = 10_000):
    for index in range(0, len(values), batch_size):
        yield values[index : index + batch_size]


async def persist_graph_fact_extraction(
    session: AsyncSession,
    *,
    run_id: str | uuid.UUID,
    site_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    task_frame_id: str | uuid.UUID,
    task_attempt_id: str | uuid.UUID,
    source_url: str | None,
    output: GraphFactExtractionOutput,
) -> PersistGraphFactsResult:
    run_uuid = _as_uuid(run_id)
    site_uuid = _as_uuid(site_id)
    document_uuid = _as_uuid(document_id)
    task_frame_uuid = _as_uuid(task_frame_id)
    task_attempt_uuid = _as_uuid(task_attempt_id)

    entity_specs_by_key: Dict[str, dict] = {}
    for entity in output.entities:
        normalized_name = entity.normalized_name or normalize_graph_name(entity.entity_name)
        fact_key = entity.fact_key or build_graph_entity_fact_key(
            entity.entity_name,
            entity.entity_type,
            entity.evidence_text,
        )
        entity_specs_by_key[fact_key] = {
            "entity_name": entity.entity_name,
            "normalized_name": normalized_name,
            "entity_type": entity.entity_type,
            "description": entity.description,
            "evidence_text": entity.evidence_text,
            "metadata_json": entity.metadata,
        }

    existing_entity_rows_by_key: Dict[str, GraphEntityFact] = {}
    if entity_specs_by_key:
        existing_entities = await session.execute(
            select(GraphEntityFact).where(
                GraphEntityFact.run_id == run_uuid,
                GraphEntityFact.document_id == document_uuid,
                GraphEntityFact.fact_key.in_(list(entity_specs_by_key.keys())),
            )
        )
        existing_entity_rows_by_key = {row.fact_key: row for row in existing_entities.scalars()}

    entity_rows_by_key: Dict[str, GraphEntityFact] = {}
    entity_rows_by_link_key: Dict[str, GraphEntityFact] = {}
    entity_rows_by_name_key: Dict[str, GraphEntityFact] = {}
    for fact_key, spec in entity_specs_by_key.items():
        row = existing_entity_rows_by_key.get(fact_key)
        if row is None:
            row = GraphEntityFact(
                run_id=run_uuid,
                site_id=site_uuid,
                document_id=document_uuid,
                task_frame_id=task_frame_uuid,
                task_attempt_id=task_attempt_uuid,
                fact_key=fact_key,
                entity_name=spec["entity_name"],
                normalized_name=spec["normalized_name"],
                entity_type=spec["entity_type"],
                description=spec["description"],
                evidence_text=spec["evidence_text"],
                source_url=source_url,
                metadata_json=spec["metadata_json"],
            )
            session.add(row)
        else:
            row.description = _prefer_longer(row.description, spec["description"])
            row.evidence_text = _prefer_longer(row.evidence_text, spec["evidence_text"])
            row.source_url = row.source_url or source_url
            row.metadata_json = _merge_dicts(row.metadata_json, spec["metadata_json"])

        entity_rows_by_key[fact_key] = row
        entity_rows_by_link_key[f"{spec['normalized_name']}::{normalize_graph_name(spec['entity_type'])}"] = row
        entity_rows_by_name_key[spec["normalized_name"]] = row

    await session.flush()

    relationship_specs_by_key: Dict[str, dict] = {}
    for relationship in output.relationships:
        source_normalized = relationship.source_entity_normalized_name or normalize_graph_name(relationship.source_entity_name)
        target_normalized = relationship.target_entity_normalized_name or normalize_graph_name(relationship.target_entity_name)
        fact_key = relationship.fact_key or build_graph_relationship_fact_key(
            relationship.source_entity_name,
            relationship.target_entity_name,
            relationship.relationship_type,
            relationship.exact_quote,
        )
        relationship_specs_by_key[fact_key] = {
            "source_entity_name": relationship.source_entity_name,
            "source_entity_normalized_name": source_normalized,
            "source_entity_type": relationship.source_entity_type,
            "target_entity_name": relationship.target_entity_name,
            "target_entity_normalized_name": target_normalized,
            "target_entity_type": relationship.target_entity_type,
            "relationship_type": relationship.relationship_type,
            "exact_quote": relationship.exact_quote,
            "metadata_json": relationship.metadata,
        }

    existing_relationship_rows_by_key: Dict[str, GraphRelationshipFact] = {}
    if relationship_specs_by_key:
        existing_relationships = await session.execute(
            select(GraphRelationshipFact).where(
                GraphRelationshipFact.run_id == run_uuid,
                GraphRelationshipFact.document_id == document_uuid,
                GraphRelationshipFact.fact_key.in_(list(relationship_specs_by_key.keys())),
            )
        )
        existing_relationship_rows_by_key = {row.fact_key: row for row in existing_relationships.scalars()}

    relationship_rows_by_key: Dict[str, GraphRelationshipFact] = {}
    for fact_key, spec in relationship_specs_by_key.items():
        source_link_key = f"{spec['source_entity_normalized_name']}::{normalize_graph_name(spec['source_entity_type'])}"
        target_link_key = f"{spec['target_entity_normalized_name']}::{normalize_graph_name(spec['target_entity_type'])}"
        source_entity_row = entity_rows_by_link_key.get(source_link_key) or entity_rows_by_name_key.get(
            spec["source_entity_normalized_name"]
        )
        target_entity_row = entity_rows_by_link_key.get(target_link_key) or entity_rows_by_name_key.get(
            spec["target_entity_normalized_name"]
        )

        row = existing_relationship_rows_by_key.get(fact_key)
        if row is None:
            row = GraphRelationshipFact(
                run_id=run_uuid,
                site_id=site_uuid,
                document_id=document_uuid,
                task_frame_id=task_frame_uuid,
                task_attempt_id=task_attempt_uuid,
                source_entity_fact_id=source_entity_row.id if source_entity_row else None,
                target_entity_fact_id=target_entity_row.id if target_entity_row else None,
                fact_key=fact_key,
                source_entity_name=spec["source_entity_name"],
                source_entity_normalized_name=spec["source_entity_normalized_name"],
                source_entity_type=spec["source_entity_type"],
                target_entity_name=spec["target_entity_name"],
                target_entity_normalized_name=spec["target_entity_normalized_name"],
                target_entity_type=spec["target_entity_type"],
                relationship_type=spec["relationship_type"],
                exact_quote=spec["exact_quote"],
                source_url=source_url,
                metadata_json=spec["metadata_json"],
            )
            session.add(row)
        else:
            if row.source_entity_fact_id is None and source_entity_row is not None:
                row.source_entity_fact_id = source_entity_row.id
            if row.target_entity_fact_id is None and target_entity_row is not None:
                row.target_entity_fact_id = target_entity_row.id
            row.source_url = row.source_url or source_url
            row.metadata_json = _merge_dicts(row.metadata_json, spec["metadata_json"])

        relationship_rows_by_key[fact_key] = row

    await session.flush()

    return PersistGraphFactsResult(
        entity_fact_ids=[str(row.id) for row in entity_rows_by_key.values()],
        relationship_fact_ids=[str(row.id) for row in relationship_rows_by_key.values()],
    )


async def persist_canonical_entity_resolution(
    session: AsyncSession,
    *,
    run_id: str | uuid.UUID,
    site_id: str | uuid.UUID,
    task_frame_id: str | uuid.UUID,
    task_attempt_id: str | uuid.UUID,
    output: CanonicalEntityResolutionOutput,
) -> PersistCanonicalEntitiesResult:
    run_uuid = _as_uuid(run_id)
    site_uuid = _as_uuid(site_id)
    task_frame_uuid = _as_uuid(task_frame_id)
    task_attempt_uuid = _as_uuid(task_attempt_id)

    canonical_specs_by_key: Dict[str, dict] = {}
    for canonical in output.canonical_entities:
        canonical_key = canonical.canonical_key or build_canonical_entity_key(
            canonical.canonical_name,
            canonical.entity_type,
        )
        canonical_specs_by_key[canonical_key] = {
            "canonical_name": canonical.canonical_name,
            "normalized_name": canonical.normalized_name or normalize_graph_name(canonical.canonical_name),
            "entity_type": canonical.entity_type,
            "description": canonical.description,
            "aliases_json": _unique_strings(canonical.aliases),
            "resolution_confidence": canonical.resolution_confidence,
            "metadata_json": canonical.metadata,
        }

    await session.execute(
        update(CanonicalGraphEntity)
        .where(CanonicalGraphEntity.run_id == run_uuid)
        .values(status="inactive")
    )

    existing_canonical_rows_by_key: Dict[str, CanonicalGraphEntity] = {}
    if canonical_specs_by_key:
        canonical_keys = list(canonical_specs_by_key.keys())
        for key_batch in _batches(canonical_keys):
            existing_canonical_entities = await session.execute(
                select(CanonicalGraphEntity).where(
                    CanonicalGraphEntity.run_id == run_uuid,
                    CanonicalGraphEntity.canonical_key.in_(key_batch),
                )
            )
            existing_canonical_rows_by_key.update(
                {row.canonical_key: row for row in existing_canonical_entities.scalars()}
            )

    canonical_rows_by_key: Dict[str, CanonicalGraphEntity] = {}
    for canonical_key, spec in canonical_specs_by_key.items():
        row = existing_canonical_rows_by_key.get(canonical_key)
        if row is None:
            row = CanonicalGraphEntity(
                run_id=run_uuid,
                site_id=site_uuid,
                task_frame_id=task_frame_uuid,
                task_attempt_id=task_attempt_uuid,
                canonical_key=canonical_key,
                canonical_name=spec["canonical_name"],
                normalized_name=spec["normalized_name"],
                entity_type=spec["entity_type"],
                description=spec["description"],
                aliases_json=spec["aliases_json"],
                resolution_confidence=spec["resolution_confidence"],
                status="active",
                metadata_json=spec["metadata_json"],
            )
            session.add(row)
        else:
            row.canonical_name = spec["canonical_name"]
            row.normalized_name = spec["normalized_name"]
            row.entity_type = spec["entity_type"]
            row.description = _prefer_longer(row.description, spec["description"])
            row.aliases_json = _unique_strings([*(row.aliases_json or []), *spec["aliases_json"]])
            if spec["resolution_confidence"] is not None:
                row.resolution_confidence = spec["resolution_confidence"]
            row.status = "active"
            row.metadata_json = _merge_dicts(row.metadata_json, spec["metadata_json"])

        canonical_rows_by_key[canonical_key] = row

    await session.flush()

    membership_fact_ids = [_as_uuid(m.graph_entity_fact_id) for m in output.memberships]
    existing_memberships_by_fact_id: Dict[uuid.UUID, CanonicalEntityMembership] = {}
    if membership_fact_ids:
        for fact_id_batch in _batches(membership_fact_ids):
            existing_memberships = await session.execute(
                select(CanonicalEntityMembership).where(
                    CanonicalEntityMembership.run_id == run_uuid,
                    CanonicalEntityMembership.graph_entity_fact_id.in_(fact_id_batch),
                )
            )
            existing_memberships_by_fact_id.update(
                {row.graph_entity_fact_id: row for row in existing_memberships.scalars()}
            )

    membership_rows: list[CanonicalEntityMembership] = []
    for membership in output.memberships:
        fact_id = _as_uuid(membership.graph_entity_fact_id)
        canonical_key = membership.canonical_key or build_canonical_entity_key(
            membership.canonical_name,
            membership.entity_type,
        )
        canonical_row = canonical_rows_by_key.get(canonical_key)
        if canonical_row is None:
            raise ValueError(
                f"Membership for graph_entity_fact_id={membership.graph_entity_fact_id} references unknown canonical key {canonical_key}"
            )

        row = existing_memberships_by_fact_id.get(fact_id)
        if row is None:
            row = CanonicalEntityMembership(
                run_id=run_uuid,
                site_id=site_uuid,
                task_frame_id=task_frame_uuid,
                task_attempt_id=task_attempt_uuid,
                canonical_entity_id=canonical_row.id,
                graph_entity_fact_id=fact_id,
                resolution_reason=membership.resolution_reason,
                confidence=membership.confidence,
                metadata_json=membership.metadata,
            )
            session.add(row)
        else:
            row.canonical_entity_id = canonical_row.id
            row.resolution_reason = _prefer_longer(row.resolution_reason, membership.resolution_reason)
            if membership.confidence is not None:
                row.confidence = membership.confidence
            row.metadata_json = _merge_dicts(row.metadata_json, membership.metadata)

        membership_rows.append(row)

    await session.flush()

    return PersistCanonicalEntitiesResult(
        canonical_entity_ids=[str(row.id) for row in canonical_rows_by_key.values()],
        membership_ids=[str(row.id) for row in membership_rows],
    )


async def persist_canonical_relationships(
    session: AsyncSession,
    *,
    run_id: str | uuid.UUID,
    site_id: str | uuid.UUID,
    task_frame_id: str | uuid.UUID,
    task_attempt_id: str | uuid.UUID,
    output: CanonicalRelationshipAggregationOutput,
) -> PersistCanonicalRelationshipsResult:
    run_uuid = _as_uuid(run_id)
    site_uuid = _as_uuid(site_id)
    task_frame_uuid = _as_uuid(task_frame_id)
    task_attempt_uuid = _as_uuid(task_attempt_id)

    relationship_specs_by_key: Dict[str, dict] = {}
    canonical_keys: set[str] = set()
    for relationship in output.relationships:
        canonical_relationship_key = relationship.canonical_relationship_key or build_canonical_relationship_key(
            relationship.source_canonical_key,
            relationship.target_canonical_key,
            relationship.relationship_type,
        )
        canonical_keys.add(relationship.source_canonical_key)
        canonical_keys.add(relationship.target_canonical_key)
        relationship_specs_by_key[canonical_relationship_key] = {
            "source_canonical_key": relationship.source_canonical_key,
            "target_canonical_key": relationship.target_canonical_key,
            "relationship_type": relationship.relationship_type,
            "normalized_relationship_type": relationship.normalized_relationship_type
            or normalize_graph_name(relationship.relationship_type),
            "evidence_count": relationship.evidence_count,
            "weight": relationship.weight if relationship.weight is not None else float(relationship.evidence_count),
            "quotes_json": _unique_strings(relationship.quotes),
            "source_urls_json": _unique_strings(relationship.source_urls),
            "supporting_fact_ids_json": _unique_strings(relationship.supporting_fact_ids),
            "metadata_json": relationship.metadata,
        }

    await session.execute(
        update(CanonicalGraphRelationship)
        .where(CanonicalGraphRelationship.run_id == run_uuid)
        .values(status="inactive")
    )

    canonical_entities_by_key: Dict[str, CanonicalGraphEntity] = {}
    if canonical_keys:
        for key_batch in _batches(list(canonical_keys)):
            canonical_entities = await session.execute(
                select(CanonicalGraphEntity).where(
                    CanonicalGraphEntity.run_id == run_uuid,
                    CanonicalGraphEntity.status == "active",
                    CanonicalGraphEntity.canonical_key.in_(key_batch),
                )
            )
            canonical_entities_by_key.update({row.canonical_key: row for row in canonical_entities.scalars()})

    existing_relationship_rows_by_key: Dict[str, CanonicalGraphRelationship] = {}
    if relationship_specs_by_key:
        relationship_keys = list(relationship_specs_by_key.keys())
        for key_batch in _batches(relationship_keys):
            existing_relationships = await session.execute(
                select(CanonicalGraphRelationship).where(
                    CanonicalGraphRelationship.run_id == run_uuid,
                    CanonicalGraphRelationship.canonical_relationship_key.in_(key_batch),
                )
            )
            existing_relationship_rows_by_key.update(
                {row.canonical_relationship_key: row for row in existing_relationships.scalars()}
            )

    relationship_rows_by_key: Dict[str, CanonicalGraphRelationship] = {}
    for canonical_relationship_key, spec in relationship_specs_by_key.items():
        source_entity = canonical_entities_by_key.get(spec["source_canonical_key"])
        target_entity = canonical_entities_by_key.get(spec["target_canonical_key"])
        if source_entity is None or target_entity is None:
            raise ValueError(
                "Canonical relationship references missing canonical entity "
                f"(source={spec['source_canonical_key']}, target={spec['target_canonical_key']})"
            )

        row = existing_relationship_rows_by_key.get(canonical_relationship_key)
        if row is None:
            row = CanonicalGraphRelationship(
                run_id=run_uuid,
                site_id=site_uuid,
                task_frame_id=task_frame_uuid,
                task_attempt_id=task_attempt_uuid,
                source_canonical_entity_id=source_entity.id,
                target_canonical_entity_id=target_entity.id,
                canonical_relationship_key=canonical_relationship_key,
                source_canonical_key=spec["source_canonical_key"],
                target_canonical_key=spec["target_canonical_key"],
                relationship_type=spec["relationship_type"],
                normalized_relationship_type=spec["normalized_relationship_type"],
                evidence_count=spec["evidence_count"],
                weight=spec["weight"],
                quotes_json=spec["quotes_json"],
                source_urls_json=spec["source_urls_json"],
                supporting_fact_ids_json=spec["supporting_fact_ids_json"],
                status="active",
                metadata_json=spec["metadata_json"],
            )
            session.add(row)
        else:
            row.source_canonical_entity_id = source_entity.id
            row.target_canonical_entity_id = target_entity.id
            row.relationship_type = spec["relationship_type"]
            row.normalized_relationship_type = spec["normalized_relationship_type"]
            row.evidence_count = spec["evidence_count"]
            row.weight = spec["weight"]
            row.quotes_json = spec["quotes_json"]
            row.source_urls_json = spec["source_urls_json"]
            row.supporting_fact_ids_json = spec["supporting_fact_ids_json"]
            row.status = "active"
            row.metadata_json = _merge_dicts(row.metadata_json, spec["metadata_json"])

        relationship_rows_by_key[canonical_relationship_key] = row

    await session.flush()

    return PersistCanonicalRelationshipsResult(
        canonical_relationship_ids=[str(row.id) for row in relationship_rows_by_key.values()]
    )


async def persist_canonical_communities(
    session: AsyncSession,
    *,
    run_id: str | uuid.UUID,
    site_id: str | uuid.UUID,
    task_frame_id: str | uuid.UUID,
    task_attempt_id: str | uuid.UUID,
    communities: Sequence[CanonicalCommunitySpec],
) -> PersistCanonicalCommunitiesResult:
    run_uuid = _as_uuid(run_id)
    site_uuid = _as_uuid(site_id)
    task_frame_uuid = _as_uuid(task_frame_id)
    task_attempt_uuid = _as_uuid(task_attempt_id)

    community_specs_by_key: Dict[str, dict] = {}
    canonical_keys: set[str] = set()
    for community in communities:
        member_specs_by_key: Dict[str, dict] = {}
        for member in community.members:
            member_specs_by_key[member.canonical_key] = {
                "canonical_key": member.canonical_key,
                "canonical_name": member.canonical_name,
                "entity_type": member.entity_type,
                "membership_rank": member.membership_rank,
                "metadata_json": member.metadata,
            }

        member_keys = sorted(member_specs_by_key.keys())
        community_key = community.community_key or build_canonical_community_key(member_keys, community.algorithm)
        canonical_keys.update(member_keys)
        community_specs_by_key[community_key] = {
            "algorithm": community.algorithm,
            "algorithm_version": community.algorithm_version,
            "community_name": community.community_name,
            "summary": community.summary,
            "member_count": community.member_count or len(member_keys),
            "relationship_count": community.relationship_count,
            "members": [member_specs_by_key[key] for key in member_keys],
            "metadata_json": community.metadata,
        }

    canonical_entities_by_key: Dict[str, CanonicalGraphEntity] = {}
    if canonical_keys:
        for key_batch in _batches(list(canonical_keys)):
            canonical_entities = await session.execute(
                select(CanonicalGraphEntity).where(
                    CanonicalGraphEntity.run_id == run_uuid,
                    CanonicalGraphEntity.canonical_key.in_(key_batch),
                )
            )
            canonical_entities_by_key.update({row.canonical_key: row for row in canonical_entities.scalars()})

    existing_communities = await session.execute(
        select(CanonicalGraphCommunity).where(CanonicalGraphCommunity.run_id == run_uuid)
    )
    existing_communities_by_key = {row.community_key: row for row in existing_communities.scalars()}

    community_rows_by_key: Dict[str, CanonicalGraphCommunity] = {}
    for community_key, spec in community_specs_by_key.items():
        row = existing_communities_by_key.get(community_key)
        if row is None:
            row = CanonicalGraphCommunity(
                run_id=run_uuid,
                site_id=site_uuid,
                task_frame_id=task_frame_uuid,
                task_attempt_id=task_attempt_uuid,
                community_key=community_key,
                algorithm=spec["algorithm"],
                algorithm_version=spec["algorithm_version"],
                community_name=spec["community_name"],
                summary=spec["summary"],
                member_count=spec["member_count"],
                relationship_count=spec["relationship_count"],
                metadata_json=spec["metadata_json"],
            )
            session.add(row)
        else:
            row.algorithm = spec["algorithm"]
            row.algorithm_version = spec["algorithm_version"]
            row.community_name = spec["community_name"]
            row.summary = spec["summary"]
            row.member_count = spec["member_count"]
            row.relationship_count = spec["relationship_count"]
            row.status = "active"
            row.metadata_json = _merge_dicts(row.metadata_json, spec["metadata_json"])

        community_rows_by_key[community_key] = row

    await session.flush()

    existing_memberships = await session.execute(
        select(CanonicalCommunityMembership).where(CanonicalCommunityMembership.run_id == run_uuid)
    )
    existing_memberships_by_entity_id = {
        row.canonical_entity_id: row for row in existing_memberships.scalars()
    }

    membership_rows: list[CanonicalCommunityMembership] = []
    current_entity_ids: set[uuid.UUID] = set()
    for community_key, spec in community_specs_by_key.items():
        community_row = community_rows_by_key[community_key]
        for member in spec["members"]:
            canonical_row = canonical_entities_by_key.get(member["canonical_key"])
            if canonical_row is None:
                raise ValueError(
                    f"Community {community_key} references unknown canonical key {member['canonical_key']}"
                )

            current_entity_ids.add(canonical_row.id)
            row = existing_memberships_by_entity_id.get(canonical_row.id)
            if row is None:
                row = CanonicalCommunityMembership(
                    run_id=run_uuid,
                    site_id=site_uuid,
                    task_frame_id=task_frame_uuid,
                    task_attempt_id=task_attempt_uuid,
                    canonical_community_id=community_row.id,
                    canonical_entity_id=canonical_row.id,
                    membership_rank=member["membership_rank"],
                    metadata_json=member["metadata_json"],
                )
                session.add(row)
            else:
                row.canonical_community_id = community_row.id
                row.membership_rank = member["membership_rank"]
                row.metadata_json = _merge_dicts(row.metadata_json, member["metadata_json"])

            membership_rows.append(row)

    for canonical_entity_id, row in existing_memberships_by_entity_id.items():
        if canonical_entity_id not in current_entity_ids:
            await session.delete(row)

    current_community_keys = set(community_specs_by_key.keys())
    for community_key, row in existing_communities_by_key.items():
        if community_key not in current_community_keys:
            await session.delete(row)

    await session.flush()

    return PersistCanonicalCommunitiesResult(
        canonical_community_ids=[str(row.id) for row in community_rows_by_key.values()],
        membership_ids=[str(row.id) for row in membership_rows],
    )


async def persist_canonical_community_summaries(
    session: AsyncSession,
    *,
    run_id: str | uuid.UUID,
    summaries: Sequence[CommunitySummarySpec],
) -> list[str]:
    run_uuid = _as_uuid(run_id)
    community_keys = [summary.community_key for summary in summaries]
    if not community_keys:
        return []

    existing_communities = await session.execute(
        select(CanonicalGraphCommunity).where(
            CanonicalGraphCommunity.run_id == run_uuid,
            CanonicalGraphCommunity.community_key.in_(community_keys),
        )
    )
    communities_by_key = {row.community_key: row for row in existing_communities.scalars()}

    updated_rows: list[CanonicalGraphCommunity] = []
    for summary in summaries:
        row = communities_by_key.get(summary.community_key)
        if row is None:
            raise ValueError(f"Community summary references unknown community key {summary.community_key}")

        row.community_name = summary.community_name
        row.summary = summary.summary
        row.metadata_json = _merge_dicts(row.metadata_json, summary.metadata)
        updated_rows.append(row)

    await session.flush()
    return [str(row.id) for row in updated_rows]
