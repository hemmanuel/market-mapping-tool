import uuid
from collections import Counter, defaultdict

from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.events import event_manager
from src.db.neo4j_session import driver
from src.db.session import AsyncSessionLocal
from src.orchestrator.core.graph_contracts import (
    CanonicalCommunityMemberSpec,
    CanonicalCommunitySpec,
    CommunitySummarySpec,
    GraphProjectionInput,
    ProjectCommunitiesResult,
    ProjectCommunitySummariesResult,
)
from src.orchestrator.core.graph_models import (
    CanonicalCommunityMembership,
    CanonicalGraphCommunity,
    CanonicalGraphEntity,
    CanonicalGraphRelationship,
)
from src.orchestrator.core.graph_store import (
    build_canonical_community_key,
    persist_canonical_communities,
    persist_canonical_community_summaries,
)
from src.orchestrator.core.llm import BespokeLLMClient
from src.orchestrator.core.schemas import TaskFrame


class _CommunitySummaryModel(BaseModel):
    community_name: str = Field(description="A short 2-5 word name for the community.")
    summary: str = Field(description="A concise 1-2 sentence summary of what the community represents.")


def _community_graph_name(site_uuid: uuid.UUID) -> str:
    return f"canonical_communities_{site_uuid.hex}"


def _batches(values: list, batch_size: int = 5_000):
    for index in range(0, len(values), batch_size):
        yield values[index : index + batch_size]


async def _drop_gds_graph(neo4j_session, graph_name: str) -> None:
    try:
        await neo4j_session.run(f"CALL gds.graph.drop('{graph_name}', false)")
    except Exception:
        pass


class ProjectCommunitiesWorker:
    accepts_attempt_id = True

    async def execute(self, task: TaskFrame, attempt_id: str) -> ProjectCommunitiesResult:
        payload = GraphProjectionInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)
        graph_name = _community_graph_name(site_uuid)

        async with AsyncSessionLocal() as session:
            relationship_result = await session.execute(
                select(
                    CanonicalGraphRelationship.source_canonical_key,
                    CanonicalGraphRelationship.target_canonical_key,
                    CanonicalGraphRelationship.relationship_type,
                ).where(
                    CanonicalGraphRelationship.run_id == run_uuid,
                    CanonicalGraphRelationship.site_id == site_uuid,
                    CanonicalGraphRelationship.status == "active",
                )
            )
            relationship_rows = relationship_result.all()

        assignments: list[dict] = []
        async with driver.session() as neo4j_session:
            node_count_result = await neo4j_session.run(
                """
                MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id, run_id: $run_id})
                RETURN count(entity) AS count
                """,
                pipeline_id=payload.site_id,
                run_id=payload.run_id,
            )
            node_count_record = await node_count_result.single()
            node_count = int(node_count_record["count"] or 0) if node_count_record else 0

            if node_count > 0:
                await _drop_gds_graph(neo4j_session, graph_name)
                try:
                    site_value = str(site_uuid)
                    run_value = payload.run_id
                    node_query = (
                        "MATCH (n:CanonicalEntity "
                        f"{{pipeline_id: '{site_value}', run_id: '{run_value}'}}) "
                        "RETURN id(n) AS id"
                    )
                    relationship_query = (
                        "MATCH "
                        f"(s:CanonicalEntity {{pipeline_id: '{site_value}', run_id: '{run_value}'}})"
                        f"-[:INTERACTS_WITH {{pipeline_id: '{site_value}', run_id: '{run_value}'}}]->"
                        f"(t:CanonicalEntity {{pipeline_id: '{site_value}', run_id: '{run_value}'}}) "
                        "RETURN id(s) AS source, id(t) AS target"
                    )
                    await neo4j_session.run(
                        "CALL gds.graph.project.cypher($graph_name, $node_query, $relationship_query)",
                        graph_name=graph_name,
                        node_query=node_query,
                        relationship_query=relationship_query,
                    )
                    assignment_result = await neo4j_session.run(
                        "CALL gds.louvain.stream($graph_name) YIELD nodeId, communityId RETURN nodeId, communityId",
                        graph_name=graph_name,
                    )
                    assignments = await assignment_result.data()
                finally:
                    await _drop_gds_graph(neo4j_session, graph_name)

        node_rows: list[dict] = []
        if assignments:
            node_ids = [int(assignment["nodeId"]) for assignment in assignments]
            async with driver.session() as neo4j_session:
                for node_id_batch in _batches(node_ids):
                    node_result = await neo4j_session.run(
                        """
                        MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id, run_id: $run_id})
                        WHERE id(entity) IN $node_ids
                        RETURN id(entity) AS node_id,
                               entity.canonical_key AS canonical_key,
                               entity.name AS canonical_name,
                               entity.type AS entity_type
                        """,
                        pipeline_id=payload.site_id,
                        run_id=payload.run_id,
                        node_ids=node_id_batch,
                    )
                    node_rows.extend(await node_result.data())

        node_rows_by_id = {int(row["node_id"]): row for row in node_rows}
        degree_by_key: Counter[str] = Counter()
        relationship_count_by_key: Counter[str] = Counter()
        relationship_type_counts_by_key: dict[str, Counter[str]] = defaultdict(Counter)

        member_rows_by_community_id: dict[int, list[dict]] = defaultdict(list)
        for assignment in assignments:
            node_row = node_rows_by_id.get(int(assignment["nodeId"]))
            if node_row is None or not node_row.get("canonical_key"):
                continue
            member_rows_by_community_id[int(assignment["communityId"])].append(node_row)

        community_id_by_key: dict[str, int] = {}
        for raw_community_id, member_rows in member_rows_by_community_id.items():
            for row in member_rows:
                canonical_key = row.get("canonical_key")
                if canonical_key:
                    community_id_by_key[canonical_key] = raw_community_id

        for source_key, target_key, relationship_type in relationship_rows:
            if source_key:
                degree_by_key[source_key] += 1
            if target_key:
                degree_by_key[target_key] += 1
            source_community_id = community_id_by_key.get(source_key)
            if source_community_id is not None and source_community_id == community_id_by_key.get(target_key):
                community_id_key = str(source_community_id)
                relationship_count_by_key[community_id_key] += 1
                relationship_type_counts_by_key[community_id_key][relationship_type] += 1

        community_specs: list[CanonicalCommunitySpec] = []
        for raw_community_id, member_rows in member_rows_by_community_id.items():
            member_keys = {row["canonical_key"] for row in member_rows if row.get("canonical_key")}
            sorted_member_rows = sorted(
                member_rows,
                key=lambda row: (
                    -(degree_by_key.get(row["canonical_key"], 0)),
                    str(row.get("canonical_name") or ""),
                ),
            )
            members = [
                CanonicalCommunityMemberSpec(
                    canonical_key=row["canonical_key"],
                    canonical_name=row.get("canonical_name"),
                    entity_type=row.get("entity_type"),
                    membership_rank=index + 1,
                    metadata={"degree": degree_by_key.get(row["canonical_key"], 0)},
                )
                for index, row in enumerate(sorted_member_rows)
            ]
            community_key = build_canonical_community_key([member.canonical_key for member in members])
            relationship_types = relationship_type_counts_by_key.get(str(raw_community_id), Counter())
            community_specs.append(
                CanonicalCommunitySpec(
                    community_key=community_key,
                    algorithm="louvain",
                    algorithm_version="neo4j-gds",
                    community_name=f"Community {raw_community_id}",
                    member_count=len(members),
                    relationship_count=int(relationship_count_by_key.get(str(raw_community_id), 0)),
                    members=members,
                    metadata={
                        "gds_community_id": raw_community_id,
                        "top_relationship_types": [
                            {"type": relationship_type, "count": count}
                            for relationship_type, count in relationship_types.most_common(10)
                        ],
                    },
                )
            )

        async with AsyncSessionLocal() as session:
            persist_result = await persist_canonical_communities(
                session,
                run_id=payload.run_id,
                site_id=payload.site_id,
                task_frame_id=task.task_id,
                task_attempt_id=attempt_id,
                communities=community_specs,
            )
            await session.commit()

        community_rows = [
            {
                "community_key": community.community_key,
                "community_id": str(community.metadata.get("gds_community_id", community.community_key)),
                "community_name": community.community_name,
                "summary": community.summary,
                "algorithm": community.algorithm,
                "algorithm_version": community.algorithm_version,
                "member_count": community.member_count,
                "relationship_count": community.relationship_count,
                "run_id": payload.run_id,
            }
            for community in community_specs
        ]
        membership_rows = [
            {
                "community_key": community.community_key,
                "community_id": str(community.metadata.get("gds_community_id", community.community_key)),
                "community_name": community.community_name,
                "canonical_key": member.canonical_key,
                "membership_rank": member.membership_rank,
                "run_id": payload.run_id,
            }
            for community in community_specs
            for member in community.members
        ]

        async with driver.session() as neo4j_session:
            if community_rows:
                await neo4j_session.run(
                    """
                    MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id})-[membership:BELONGS_TO]->(:Community {pipeline_id: $pipeline_id})
                    DELETE membership
                    """,
                    pipeline_id=payload.site_id,
                )
                await neo4j_session.run(
                    """
                    MATCH (community:Community {pipeline_id: $pipeline_id})
                    DETACH DELETE community
                    """,
                    pipeline_id=payload.site_id,
                )
                for batch in _batches(community_rows):
                    await neo4j_session.run(
                        """
                        UNWIND $communities AS community
                        MERGE (node:Community {community_key: community.community_key, pipeline_id: $pipeline_id})
                        SET node.community_id = community.community_id,
                            node.name = community.community_name,
                            node.summary = community.summary,
                            node.algorithm = community.algorithm,
                            node.algorithm_version = community.algorithm_version,
                            node.member_count = community.member_count,
                            node.relationship_count = community.relationship_count,
                            node.run_id = community.run_id
                        """,
                        communities=batch,
                        pipeline_id=payload.site_id,
                    )
                for batch in _batches(membership_rows):
                    await neo4j_session.run(
                        """
                        UNWIND $memberships AS membership
                        MATCH (entity:CanonicalEntity {
                            canonical_key: membership.canonical_key,
                            pipeline_id: $pipeline_id,
                            run_id: $run_id
                        })
                        MATCH (community:Community {community_key: membership.community_key, pipeline_id: $pipeline_id})
                        SET entity.community_key = membership.community_key,
                            entity.community_id = membership.community_id,
                            entity.community_name = membership.community_name,
                            entity.community_rank = membership.membership_rank
                        MERGE (entity)-[relationship:BELONGS_TO {community_key: membership.community_key}]->(community)
                        SET relationship.pipeline_id = $pipeline_id,
                            relationship.run_id = membership.run_id,
                            relationship.membership_rank = membership.membership_rank
                        """,
                        memberships=batch,
                        pipeline_id=payload.site_id,
                        run_id=payload.run_id,
                    )
            else:
                await neo4j_session.run(
                    """
                    MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id})-[membership:BELONGS_TO]->(:Community {pipeline_id: $pipeline_id})
                    DELETE membership
                    """,
                    pipeline_id=payload.site_id,
                )
                await neo4j_session.run(
                    """
                    MATCH (community:Community {pipeline_id: $pipeline_id})
                    DETACH DELETE community
                    """,
                    pipeline_id=payload.site_id,
                )
                await neo4j_session.run(
                    """
                    MATCH (entity:CanonicalEntity {pipeline_id: $pipeline_id})
                    REMOVE entity.community_key, entity.community_id, entity.community_name, entity.community_summary, entity.community_rank
                    """,
                    pipeline_id=payload.site_id,
                )

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    "[ProjectCommunities] Persisted and projected "
                    f"{len(community_rows)} community node(s) and {len(membership_rows)} community membership(s)."
                ),
            },
        )
        return ProjectCommunitiesResult(
            canonical_community_ids=persist_result.canonical_community_ids,
            membership_ids=persist_result.membership_ids,
            projected_communities=len(community_rows),
            projected_memberships=len(membership_rows),
        )


class ProjectCommunitySummariesWorker:
    accepts_attempt_id = True

    def __init__(self, llm_client: BespokeLLMClient):
        self.llm_client = llm_client

    async def execute(self, task: TaskFrame, attempt_id: str) -> ProjectCommunitySummariesResult:
        payload = GraphProjectionInput(**task.payload)
        run_uuid = uuid.UUID(payload.run_id)
        site_uuid = uuid.UUID(payload.site_id)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    CanonicalGraphCommunity.community_key,
                    CanonicalGraphCommunity.community_name,
                    CanonicalGraphCommunity.member_count,
                    CanonicalGraphCommunity.relationship_count,
                    CanonicalGraphCommunity.metadata_json,
                    CanonicalCommunityMembership.membership_rank,
                    CanonicalGraphEntity.canonical_name,
                    CanonicalGraphEntity.entity_type,
                )
                .join(
                    CanonicalCommunityMembership,
                    CanonicalCommunityMembership.canonical_community_id == CanonicalGraphCommunity.id,
                )
                .join(CanonicalGraphEntity, CanonicalGraphEntity.id == CanonicalCommunityMembership.canonical_entity_id)
                .where(
                    CanonicalGraphCommunity.run_id == run_uuid,
                    CanonicalGraphCommunity.site_id == site_uuid,
                )
                .order_by(
                    CanonicalGraphCommunity.community_key.asc(),
                    CanonicalCommunityMembership.membership_rank.asc(),
                    CanonicalGraphEntity.canonical_name.asc(),
                )
            )
            rows = result.all()

        community_rows_by_key: dict[str, dict] = {}
        for (
            community_key,
            community_name,
            member_count,
            relationship_count,
            metadata_json,
            membership_rank,
            canonical_name,
            entity_type,
        ) in rows:
            community_entry = community_rows_by_key.setdefault(
                community_key,
                {
                    "community_name": community_name,
                    "member_count": member_count,
                    "relationship_count": relationship_count,
                    "metadata_json": metadata_json if isinstance(metadata_json, dict) else {},
                    "members": [],
                },
            )
            community_entry["members"].append(
                {
                    "canonical_name": canonical_name,
                    "entity_type": entity_type,
                    "membership_rank": membership_rank,
                }
            )

        summary_specs: list[CommunitySummarySpec] = []
        for community_key, community_data in community_rows_by_key.items():
            if len(community_data["members"]) < 3:
                continue

            top_members = community_data["members"][:25]
            member_lines = "\n".join(
                f"- {member['canonical_name']} ({member['entity_type'] or 'Unknown'})"
                for member in top_members
                if member.get("canonical_name")
            )
            relationship_type_lines = "\n".join(
                f"- {relationship['type']}: {relationship['count']}"
                for relationship in community_data["metadata_json"].get("top_relationship_types", [])
            )
            prompt = (
                "You are a market intelligence analyst summarizing a community in a knowledge graph.\n"
                "Return a short, specific community name (2-5 words) and a concise 1-2 sentence summary.\n"
                "Avoid generic labels like 'Business Cluster' or 'Market Group'.\n\n"
                f"Detected member count: {community_data['member_count']}\n"
                f"Internal relationship count: {community_data['relationship_count']}\n\n"
                "Top members:\n"
                f"{member_lines or '- None'}\n\n"
                "Dominant relationship types:\n"
                f"{relationship_type_lines or '- None'}\n"
            )
            summary = await self.llm_client.generate_structured(prompt, _CommunitySummaryModel)
            summary_specs.append(
                CommunitySummarySpec(
                    community_key=community_key,
                    community_name=summary.community_name.strip(),
                    summary=summary.summary.strip(),
                    metadata={
                        "summary_model": self.llm_client.model,
                        "summary_task_frame_id": task.task_id,
                        "summary_task_attempt_id": attempt_id,
                    },
                )
            )

        async with AsyncSessionLocal() as session:
            await persist_canonical_community_summaries(
                session,
                run_id=payload.run_id,
                summaries=summary_specs,
            )
            await session.commit()

        if summary_specs:
            summary_rows = [
                {
                    "community_key": summary.community_key,
                    "community_name": summary.community_name,
                    "summary": summary.summary,
                }
                for summary in summary_specs
            ]
            async with driver.session() as neo4j_session:
                await neo4j_session.run(
                    """
                    UNWIND $summaries AS summary
                    MATCH (community:Community {community_key: summary.community_key, pipeline_id: $pipeline_id})
                    SET community.name = summary.community_name,
                        community.summary = summary.summary
                    WITH summary
                    MATCH (entity:CanonicalEntity {
                        pipeline_id: $pipeline_id,
                        run_id: $run_id,
                        community_key: summary.community_key
                    })
                    SET entity.community_name = summary.community_name,
                        entity.community_summary = summary.summary
                    """,
                    summaries=summary_rows,
                    pipeline_id=payload.site_id,
                    run_id=payload.run_id,
                )

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    "[ProjectCommunitySummaries] Generated summaries for "
                    f"{len(summary_specs)} communit(y/ies)."
                ),
            },
        )
        return ProjectCommunitySummariesResult(summarized_communities=len(summary_specs))
