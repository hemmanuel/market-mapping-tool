import uuid

from sqlalchemy import func, select

from src.api.events import event_manager
from src.db.neo4j_session import driver
from src.db.session import AsyncSessionLocal
from src.models.relational import Document as PGDocument
from src.models.relational import Site
from src.orchestrator.core.graph_contracts import (
    GraphProjectionInput,
    PruneGraphResult,
    PublishGraphReadyResult,
    build_document_mention_key,
)
from src.orchestrator.core.ledger_models import OrchestrationTaskFrameRecord, TaskAttempt
from src.orchestrator.core.graph_models import (
    CanonicalCommunityMembership,
    CanonicalGraphCommunity,
    CanonicalEntityMembership,
    CanonicalGraphEntity,
    CanonicalGraphRelationship,
    GraphEntityFact,
)
from src.orchestrator.core.schemas import TaskFrame


def _extract_source_url(metadata_json: dict | None) -> str | None:
    if not isinstance(metadata_json, dict):
        return None

    source_url = metadata_json.get("source_url")
    if not isinstance(source_url, str):
        return None

    stripped = source_url.strip()
    return stripped or None


async def _load_expected_graph_state(run_uuid: uuid.UUID, site_uuid: uuid.UUID) -> dict[str, set[str]]:
    async with AsyncSessionLocal() as session:
        canonical_result = await session.execute(
            select(CanonicalGraphEntity.canonical_key).where(
                CanonicalGraphEntity.run_id == run_uuid,
                CanonicalGraphEntity.site_id == site_uuid,
            )
        )
        canonical_keys = {key for key in canonical_result.scalars().all() if key}

        relationship_result = await session.execute(
            select(CanonicalGraphRelationship.canonical_relationship_key).where(
                CanonicalGraphRelationship.run_id == run_uuid,
                CanonicalGraphRelationship.site_id == site_uuid,
            )
        )
        relationship_keys = {key for key in relationship_result.scalars().all() if key}

        mention_rows = await session.execute(
            select(PGDocument.metadata_json, CanonicalGraphEntity.canonical_key)
            .join(GraphEntityFact, GraphEntityFact.document_id == PGDocument.id)
            .join(CanonicalEntityMembership, CanonicalEntityMembership.graph_entity_fact_id == GraphEntityFact.id)
            .join(CanonicalGraphEntity, CanonicalGraphEntity.id == CanonicalEntityMembership.canonical_entity_id)
            .where(
                GraphEntityFact.run_id == run_uuid,
                GraphEntityFact.site_id == site_uuid,
                CanonicalEntityMembership.run_id == run_uuid,
                CanonicalGraphEntity.run_id == run_uuid,
                CanonicalGraphEntity.site_id == site_uuid,
            )
        )
        mention_records = mention_rows.all()

    document_urls: set[str] = set()
    mention_keys: set[str] = set()
    for metadata_json, canonical_key in mention_records:
        source_url = _extract_source_url(metadata_json)
        if not source_url or not canonical_key:
            continue
        document_urls.add(source_url)
        mention_keys.add(build_document_mention_key(source_url, canonical_key))

    return {
        "canonical_keys": canonical_keys,
        "relationship_keys": relationship_keys,
        "document_urls": document_urls,
        "mention_keys": mention_keys,
    }


async def _delete_with_summary(query: str, **params: object) -> tuple[int, int]:
    async with driver.session() as neo4j_session:
        result = await neo4j_session.run(query, **params)
        summary = await result.consume()
        counters = summary.counters
        return getattr(counters, "nodes_deleted", 0), getattr(counters, "relationships_deleted", 0)


async def _neo4j_count(query: str, **params: object) -> int:
    async with driver.session() as neo4j_session:
        result = await neo4j_session.run(query, **params)
        record = await result.single()
        if not record:
            return 0
        return int(record["count"] or 0)


async def _load_task_output_metric(run_uuid: uuid.UUID, task_type: str, output_key: str) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TaskAttempt.output_json)
            .join(OrchestrationTaskFrameRecord, TaskAttempt.task_frame_id == OrchestrationTaskFrameRecord.id)
            .where(
                OrchestrationTaskFrameRecord.run_id == run_uuid,
                OrchestrationTaskFrameRecord.task_type == task_type,
                TaskAttempt.status == "completed",
            )
            .order_by(TaskAttempt.finished_at.desc())
            .limit(1)
        )
        output_json = result.scalar()

    if not isinstance(output_json, dict):
        return 0

    return int(output_json.get(output_key, 0) or 0)


class PruneGraphWorker:
    async def execute(self, task: TaskFrame) -> PruneGraphResult:
        payload = GraphProjectionInput(**task.payload)
        expected_state = await _load_expected_graph_state(
            run_uuid=uuid.UUID(payload.run_id),
            site_uuid=uuid.UUID(payload.site_id),
        )

        mention_keys = sorted(expected_state["mention_keys"])
        if mention_keys:
            _, deleted_mentions = await _delete_with_summary(
                """
                MATCH (d:Document {pipeline_id: $pipeline_id})-[m:MENTIONS]->(c:CanonicalEntity {pipeline_id: $pipeline_id})
                WHERE m.mention_key IS NULL OR NOT m.mention_key IN $mention_keys
                DELETE m
                """,
                pipeline_id=payload.site_id,
                mention_keys=mention_keys,
            )
        else:
            _, deleted_mentions = await _delete_with_summary(
                """
                MATCH (:Document {pipeline_id: $pipeline_id})-[m:MENTIONS]->(:CanonicalEntity {pipeline_id: $pipeline_id})
                DELETE m
                """,
                pipeline_id=payload.site_id,
            )

        document_urls = sorted(expected_state["document_urls"])
        if document_urls:
            deleted_documents, _ = await _delete_with_summary(
                """
                MATCH (d:Document {pipeline_id: $pipeline_id})
                WHERE d.url IS NULL OR NOT d.url IN $document_urls
                DETACH DELETE d
                """,
                pipeline_id=payload.site_id,
                document_urls=document_urls,
            )
        else:
            deleted_documents, _ = await _delete_with_summary(
                """
                MATCH (d:Document {pipeline_id: $pipeline_id})
                DETACH DELETE d
                """,
                pipeline_id=payload.site_id,
            )

        canonical_keys = sorted(expected_state["canonical_keys"])
        if canonical_keys:
            deleted_entities, _ = await _delete_with_summary(
                """
                MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
                WHERE c.run_id IS NULL
                   OR c.run_id <> $run_id
                   OR c.canonical_key IS NULL
                   OR NOT c.canonical_key IN $canonical_keys
                DETACH DELETE c
                """,
                pipeline_id=payload.site_id,
                run_id=payload.run_id,
                canonical_keys=canonical_keys,
            )
        else:
            deleted_entities, _ = await _delete_with_summary(
                """
                MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
                DETACH DELETE c
                """,
                pipeline_id=payload.site_id,
            )

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    "[PruneGraph] Removed "
                    f"{deleted_entities} stale canonical entit(y/ies), "
                    f"{deleted_documents} stale document node(s), and "
                    f"{deleted_mentions} stale mention edge(s)."
                ),
            },
        )
        return PruneGraphResult(
            deleted_documents=deleted_documents,
            deleted_entities=deleted_entities,
            deleted_mentions=deleted_mentions,
        )


class PublishGraphReadyWorker:
    async def execute(self, task: TaskFrame) -> PublishGraphReadyResult:
        payload = GraphProjectionInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)
        expected_state = await _load_expected_graph_state(
            run_uuid=run_uuid,
            site_uuid=site_uuid,
        )

        expected_counts = {
            "canonical_entities": len(expected_state["canonical_keys"]),
            "documents": len(expected_state["document_urls"]),
            "mentions": len(expected_state["mention_keys"]),
            "relationships": len(expected_state["relationship_keys"]),
            "similarity_edges": await _load_task_output_metric(
                run_uuid,
                "PROJECT_SEMANTIC_SIMILARITY",
                "projected_similarity_edges",
            ),
        }
        async with AsyncSessionLocal() as session:
            expected_counts["communities"] = (
                await session.scalar(
                    select(func.count())
                    .select_from(CanonicalGraphCommunity)
                    .where(
                        CanonicalGraphCommunity.run_id == run_uuid,
                        CanonicalGraphCommunity.site_id == site_uuid,
                    )
                )
                or 0
            )
            expected_counts["community_memberships"] = (
                await session.scalar(
                    select(func.count())
                    .select_from(CanonicalCommunityMembership)
                    .where(
                        CanonicalCommunityMembership.run_id == run_uuid,
                        CanonicalCommunityMembership.site_id == site_uuid,
                    )
                )
                or 0
            )

        actual_counts = {
            "canonical_entities": await _neo4j_count(
                """
                MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
                RETURN count(c) AS count
                """,
                pipeline_id=payload.site_id,
            ),
            "documents": await _neo4j_count(
                """
                MATCH (d:Document {pipeline_id: $pipeline_id})
                RETURN count(d) AS count
                """,
                pipeline_id=payload.site_id,
            ),
            "mentions": await _neo4j_count(
                """
                MATCH (:Document {pipeline_id: $pipeline_id})-[m:MENTIONS]->(:CanonicalEntity {pipeline_id: $pipeline_id})
                RETURN count(m) AS count
                """,
                pipeline_id=payload.site_id,
            ),
            "relationships": await _neo4j_count(
                """
                MATCH (:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH {pipeline_id: $pipeline_id}]->(:CanonicalEntity {pipeline_id: $pipeline_id})
                RETURN count(r) AS count
                """,
                pipeline_id=payload.site_id,
            ),
            "similarity_edges": await _neo4j_count(
                """
                MATCH (:Document {pipeline_id: $pipeline_id})-[r:SIMILAR_TO {pipeline_id: $pipeline_id}]->(:Document {pipeline_id: $pipeline_id})
                RETURN count(r) AS count
                """,
                pipeline_id=payload.site_id,
            ),
            "communities": await _neo4j_count(
                """
                MATCH (community:Community {pipeline_id: $pipeline_id})
                RETURN count(community) AS count
                """,
                pipeline_id=payload.site_id,
            ),
            "community_memberships": await _neo4j_count(
                """
                MATCH (:CanonicalEntity {pipeline_id: $pipeline_id})-[r:BELONGS_TO {pipeline_id: $pipeline_id}]->(:Community {pipeline_id: $pipeline_id})
                RETURN count(r) AS count
                """,
                pipeline_id=payload.site_id,
            ),
        }

        mismatches = [
            f"{field} expected {expected_counts[field]} got {actual_counts[field]}"
            for field in expected_counts
            if expected_counts[field] != actual_counts[field]
        ]
        if mismatches:
            raise RuntimeError(f"Graph projection verification failed: {'; '.join(mismatches)}")

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Site).where(Site.id == site_uuid))
            site = result.scalars().first()
            if site:
                site.graph_status = "ready"
                await session.commit()

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    "[PublishGraphReady] Verified bespoke graph projection "
                    f"({actual_counts['canonical_entities']} entities, "
                    f"{actual_counts['documents']} documents, "
                    f"{actual_counts['mentions']} mentions, "
                    f"{actual_counts['relationships']} relationships, "
                    f"{actual_counts['similarity_edges']} similarity edges, "
                    f"{actual_counts['communities']} communities, "
                    f"{actual_counts['community_memberships']} community memberships)."
                ),
            },
        )
        return PublishGraphReadyResult(
            ready=True,
            graph_status="ready",
            canonical_entity_count=actual_counts["canonical_entities"],
            document_count=actual_counts["documents"],
            mention_count=actual_counts["mentions"],
            relationship_count=actual_counts["relationships"],
            similarity_edge_count=actual_counts["similarity_edges"],
            community_count=actual_counts["communities"],
            community_membership_count=actual_counts["community_memberships"],
        )
