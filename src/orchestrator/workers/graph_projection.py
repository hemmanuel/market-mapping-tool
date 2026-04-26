import hashlib
import uuid

import numpy as np
from sqlalchemy import select

from src.api.events import event_manager
from src.db.neo4j_session import driver
from src.db.session import AsyncSessionLocal
from src.models.relational import Document as PGDocument
from src.orchestrator.core.graph_contracts import (
    GraphProjectionInput,
    ProjectCanonicalEntitiesResult,
    ProjectDocumentMentionsResult,
    ProjectInteractsWithResult,
    ProjectSemanticSimilarityResult,
    build_document_mention_key,
)
from src.orchestrator.core.graph_models import (
    CanonicalEntityMembership,
    CanonicalGraphEntity,
    CanonicalGraphRelationship,
    GraphEntityFact,
)
from src.orchestrator.core.schemas import TaskFrame


def _infer_document_type(source_url: str | None) -> str:
    if not source_url:
        return "html"
    lowered = source_url.lower()
    if lowered.endswith(".pdf"):
        return "pdf"
    if lowered.endswith(".docx"):
        return "docx"
    if lowered.endswith(".pptx"):
        return "pptx"
    if lowered.endswith(".xlsx") or lowered.endswith(".csv"):
        return "spreadsheet"
    return "html"


def _normalize_embedding(embedding: list[float] | None) -> np.ndarray | None:
    if embedding is None:
        return None

    vector = np.asarray(embedding, dtype=np.float32)
    if vector.size == 0:
        return None

    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm == 0.0:
        return None

    return vector / norm


def _build_similarity_key(source_url: str, target_url: str) -> str:
    ordered_urls = sorted((source_url, target_url))
    raw_key = f"{ordered_urls[0]}\n{ordered_urls[1]}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _batches(values: list[dict], batch_size: int = 5_000):
    for index in range(0, len(values), batch_size):
        yield values[index : index + batch_size]


class ProjectCanonicalEntitiesWorker:
    async def execute(self, task: TaskFrame) -> ProjectCanonicalEntitiesResult:
        payload = GraphProjectionInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CanonicalGraphEntity).where(
                    CanonicalGraphEntity.run_id == run_uuid,
                    CanonicalGraphEntity.site_id == site_uuid,
                    CanonicalGraphEntity.status == "active",
                )
            )
            entities = result.scalars().all()

        projection_rows = [
            {
                "canonical_key": entity.canonical_key,
                "canonical_name": entity.canonical_name,
                "entity_type": entity.entity_type,
                "description": entity.description,
                "aliases": entity.aliases_json or [],
                "run_id": payload.run_id,
            }
            for entity in entities
        ]

        async with driver.session() as neo4j_session:
            if projection_rows:
                await neo4j_session.run(
                    """
                    MATCH (c:CanonicalEntity {pipeline_id: $pipeline_id})
                    WHERE c.run_id IS NULL
                       OR c.run_id <> $run_id
                    DETACH DELETE c
                    """,
                    pipeline_id=payload.site_id,
                    run_id=payload.run_id,
                )
                for batch in _batches(projection_rows):
                    await neo4j_session.run(
                        """
                        UNWIND $entities AS entity
                        MERGE (c:CanonicalEntity {canonical_key: entity.canonical_key, pipeline_id: $pipeline_id})
                        SET c.name = entity.canonical_name,
                            c.type = entity.entity_type,
                            c.description = entity.description,
                            c.aliases = entity.aliases,
                            c.run_id = entity.run_id
                        """,
                        entities=batch,
                        pipeline_id=payload.site_id,
                    )
            else:
                await neo4j_session.run(
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
                "message": f"[ProjectCanonicalEntities] Projected {len(projection_rows)} canonical entit(y/ies) into Neo4j.",
            },
        )
        return ProjectCanonicalEntitiesResult(projected_entities=len(projection_rows))


class ProjectDocumentMentionsWorker:
    async def execute(self, task: TaskFrame) -> ProjectDocumentMentionsResult:
        payload = GraphProjectionInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    PGDocument.id,
                    PGDocument.title,
                    PGDocument.metadata_json,
                    CanonicalGraphEntity.canonical_key,
                    CanonicalGraphEntity.canonical_name,
                )
                .join(GraphEntityFact, GraphEntityFact.document_id == PGDocument.id)
                .join(CanonicalEntityMembership, CanonicalEntityMembership.graph_entity_fact_id == GraphEntityFact.id)
                .join(CanonicalGraphEntity, CanonicalGraphEntity.id == CanonicalEntityMembership.canonical_entity_id)
                .where(
                    GraphEntityFact.run_id == run_uuid,
                    GraphEntityFact.site_id == site_uuid,
                    CanonicalEntityMembership.run_id == run_uuid,
                    CanonicalGraphEntity.run_id == run_uuid,
                    CanonicalGraphEntity.status == "active",
                )
            )
            rows = result.all()

        documents_by_url: dict[str, dict] = {}
        mentions_by_key: dict[tuple[str, str], dict] = {}
        for document_id, title, metadata_json, canonical_key, _canonical_name in rows:
            metadata = metadata_json if isinstance(metadata_json, dict) else {}
            source_url = metadata.get("source_url")
            if not source_url:
                continue

            document_entry = documents_by_url.setdefault(
                source_url,
                {
                    "url": source_url,
                    "title": title or source_url,
                    "type": _infer_document_type(source_url),
                    "document_ids": [],
                    "run_id": payload.run_id,
                },
            )
            document_entry["document_ids"].append(str(document_id))

            mention_key = (source_url, canonical_key)
            mention_entry = mentions_by_key.setdefault(
                mention_key,
                {
                    "url": source_url,
                    "canonical_key": canonical_key,
                    "mention_key": build_document_mention_key(source_url, canonical_key),
                    "chunk_count": 0,
                    "run_id": payload.run_id,
                },
            )
            mention_entry["chunk_count"] += 1

        documents = []
        for document in documents_by_url.values():
            document["document_ids"] = sorted(set(document["document_ids"]))
            documents.append(document)

        mentions = list(mentions_by_key.values())

        if documents or mentions:
            async with driver.session() as neo4j_session:
                if documents:
                    await neo4j_session.run(
                        """
                        MATCH (d:Document {pipeline_id: $pipeline_id})
                        WHERE d.run_id IS NULL OR d.run_id <> $run_id
                        DETACH DELETE d
                        """,
                        pipeline_id=payload.site_id,
                        run_id=payload.run_id,
                    )
                    for batch in _batches(documents):
                        await neo4j_session.run(
                            """
                            UNWIND $documents AS document
                            MERGE (d:Document {url: document.url, pipeline_id: $pipeline_id})
                            SET d.title = document.title,
                                d.type = document.type,
                                d.document_ids = document.document_ids,
                                d.run_id = document.run_id
                            """,
                            documents=batch,
                            pipeline_id=payload.site_id,
                        )

                if mentions:
                    await neo4j_session.run(
                        """
                        MATCH (d:Document {pipeline_id: $pipeline_id})-[m:MENTIONS]->(c:CanonicalEntity {pipeline_id: $pipeline_id})
                        WHERE m.run_id IS NULL OR m.run_id <> $run_id
                        DELETE m
                        """,
                        pipeline_id=payload.site_id,
                        run_id=payload.run_id,
                    )

                    for batch in _batches(mentions):
                        await neo4j_session.run(
                            """
                            UNWIND $mentions AS mention
                            MATCH (d:Document {url: mention.url, pipeline_id: $pipeline_id})
                            MATCH (c:CanonicalEntity {
                                canonical_key: mention.canonical_key,
                                pipeline_id: $pipeline_id,
                                run_id: $run_id
                            })
                            MERGE (d)-[m:MENTIONS {mention_key: mention.mention_key}]->(c)
                            SET m.pipeline_id = $pipeline_id,
                                m.run_id = mention.run_id,
                                m.canonical_key = mention.canonical_key,
                                m.weight = mention.chunk_count,
                                m.chunk_count = mention.chunk_count,
                                m.source_urls = [mention.url]
                            """,
                            mentions=batch,
                            pipeline_id=payload.site_id,
                            run_id=payload.run_id,
                        )
                else:
                    await neo4j_session.run(
                        """
                        MATCH (:Document {pipeline_id: $pipeline_id})-[m:MENTIONS]->(:CanonicalEntity {pipeline_id: $pipeline_id})
                        DELETE m
                        """,
                        pipeline_id=payload.site_id,
                    )

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    f"[ProjectDocumentMentions] Projected {len(documents)} document node(s) and "
                    f"{len(mentions)} MENTIONS edge(s) into Neo4j."
                ),
            },
        )
        return ProjectDocumentMentionsResult(
            projected_documents=len(documents),
            projected_mentions=len(mentions),
        )


class ProjectInteractsWithWorker:
    async def execute(self, task: TaskFrame) -> ProjectInteractsWithResult:
        payload = GraphProjectionInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CanonicalGraphRelationship).where(
                    CanonicalGraphRelationship.run_id == run_uuid,
                    CanonicalGraphRelationship.site_id == site_uuid,
                    CanonicalGraphRelationship.status == "active",
                )
            )
            relationships = result.scalars().all()

        projection_rows = [
            {
                "canonical_relationship_key": relationship.canonical_relationship_key,
                "source_canonical_key": relationship.source_canonical_key,
                "target_canonical_key": relationship.target_canonical_key,
                "relationship_type": relationship.relationship_type,
                "weight": relationship.weight,
                "evidence_count": relationship.evidence_count,
                "quotes": relationship.quotes_json or [],
                "source_urls": relationship.source_urls_json or [],
                "run_id": payload.run_id,
            }
            for relationship in relationships
        ]

        async with driver.session() as neo4j_session:
            if projection_rows:
                await neo4j_session.run(
                    """
                    MATCH (:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH]->(:CanonicalEntity {pipeline_id: $pipeline_id})
                    WHERE r.run_id IS NULL OR r.run_id <> $run_id
                    DELETE r
                    """,
                    pipeline_id=payload.site_id,
                    run_id=payload.run_id,
                )

                for batch in _batches(projection_rows):
                    await neo4j_session.run(
                        """
                        UNWIND $relationships AS relationship
                        MATCH (s:CanonicalEntity {
                            canonical_key: relationship.source_canonical_key,
                            pipeline_id: $pipeline_id,
                            run_id: $run_id
                        })
                        MATCH (t:CanonicalEntity {
                            canonical_key: relationship.target_canonical_key,
                            pipeline_id: $pipeline_id,
                            run_id: $run_id
                        })
                        MERGE (s)-[r:INTERACTS_WITH {canonical_relationship_key: relationship.canonical_relationship_key}]->(t)
                        SET r.type = relationship.relationship_type,
                            r.pipeline_id = $pipeline_id,
                            r.weight = relationship.weight,
                            r.evidence_count = relationship.evidence_count,
                            r.quotes = relationship.quotes,
                            r.source_urls = relationship.source_urls,
                            r.run_id = relationship.run_id
                        """,
                        relationships=batch,
                        pipeline_id=payload.site_id,
                        run_id=payload.run_id,
                    )
            else:
                await neo4j_session.run(
                    """
                    MATCH (:CanonicalEntity {pipeline_id: $pipeline_id})-[r:INTERACTS_WITH]->(:CanonicalEntity {pipeline_id: $pipeline_id})
                    DELETE r
                    """,
                    pipeline_id=payload.site_id,
                )

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": f"[ProjectInteractsWith] Projected {len(projection_rows)} INTERACTS_WITH edge(s) into Neo4j.",
            },
        )
        return ProjectInteractsWithResult(projected_relationships=len(projection_rows))


class ProjectSemanticSimilarityWorker:
    SIMILARITY_THRESHOLD = 0.85

    async def execute(self, task: TaskFrame) -> ProjectSemanticSimilarityResult:
        payload = GraphProjectionInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)

        async with AsyncSessionLocal() as session:
            document_id_result = await session.execute(
                select(GraphEntityFact.document_id)
                .join(CanonicalEntityMembership, CanonicalEntityMembership.graph_entity_fact_id == GraphEntityFact.id)
                .where(
                    GraphEntityFact.run_id == run_uuid,
                    GraphEntityFact.site_id == site_uuid,
                    CanonicalEntityMembership.run_id == run_uuid,
                )
                .distinct()
            )
            document_ids = [document_id for document_id in document_id_result.scalars().all() if document_id]

            rows = []
            if document_ids:
                document_result = await session.execute(
                    select(PGDocument.metadata_json, PGDocument.embedding).where(PGDocument.id.in_(document_ids))
                )
                rows = document_result.all()

        normalized_embeddings_by_url: dict[str, list[np.ndarray]] = {}
        for metadata_json, embedding in rows:
            metadata = metadata_json if isinstance(metadata_json, dict) else {}
            source_url = metadata.get("source_url")
            if not isinstance(source_url, str) or not source_url.strip():
                continue

            normalized_embedding = _normalize_embedding(embedding)
            if normalized_embedding is None:
                continue

            normalized_embeddings_by_url.setdefault(source_url.strip(), []).append(normalized_embedding)

        document_matrices = {
            source_url: np.vstack(vectors)
            for source_url, vectors in normalized_embeddings_by_url.items()
            if vectors
        }
        ordered_urls = sorted(document_matrices.keys())

        projection_rows: list[dict[str, str | float]] = []
        for index, source_url in enumerate(ordered_urls):
            source_matrix = document_matrices[source_url]
            for target_url in ordered_urls[index + 1 :]:
                target_matrix = document_matrices[target_url]
                max_similarity = float(np.max(source_matrix @ target_matrix.T))
                if max_similarity < self.SIMILARITY_THRESHOLD:
                    continue

                projection_rows.append(
                    {
                        "source_url": source_url,
                        "target_url": target_url,
                        "similarity_key": _build_similarity_key(source_url, target_url),
                        "weight": max_similarity,
                        "run_id": payload.run_id,
                    }
                )

        async with driver.session() as neo4j_session:
            if projection_rows:
                similarity_keys = [row["similarity_key"] for row in projection_rows]
                await neo4j_session.run(
                    """
                    MATCH (:Document {pipeline_id: $pipeline_id})-[r:SIMILAR_TO]->(:Document {pipeline_id: $pipeline_id})
                    WHERE r.similarity_key IS NULL OR NOT r.similarity_key IN $similarity_keys
                    DELETE r
                    """,
                    pipeline_id=payload.site_id,
                    similarity_keys=similarity_keys,
                )

                batch_size = 1000
                for index in range(0, len(projection_rows), batch_size):
                    batch = projection_rows[index : index + batch_size]
                    await neo4j_session.run(
                        """
                        UNWIND $edges AS edge
                        MATCH (d1:Document {url: edge.source_url, pipeline_id: $pipeline_id})
                        MATCH (d2:Document {url: edge.target_url, pipeline_id: $pipeline_id})
                        MERGE (d1)-[r:SIMILAR_TO {similarity_key: edge.similarity_key}]->(d2)
                        SET r.pipeline_id = $pipeline_id,
                            r.run_id = edge.run_id,
                            r.weight = edge.weight
                        """,
                        edges=batch,
                        pipeline_id=payload.site_id,
                    )
            else:
                await neo4j_session.run(
                    """
                    MATCH (:Document {pipeline_id: $pipeline_id})-[r:SIMILAR_TO]->(:Document {pipeline_id: $pipeline_id})
                    DELETE r
                    """,
                    pipeline_id=payload.site_id,
                )

            count_result = await neo4j_session.run(
                """
                MATCH (:Document {pipeline_id: $pipeline_id})-[r:SIMILAR_TO {pipeline_id: $pipeline_id}]->(:Document {pipeline_id: $pipeline_id})
                RETURN count(r) AS count
                """,
                pipeline_id=payload.site_id,
            )
            count_record = await count_result.single()
            projected_similarity_edges = int(count_record["count"] or 0) if count_record else 0

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    "[ProjectSemanticSimilarity] Projected "
                    f"{projected_similarity_edges} SIMILAR_TO edge(s) into Neo4j."
                ),
            },
        )
        return ProjectSemanticSimilarityResult(projected_similarity_edges=projected_similarity_edges)
