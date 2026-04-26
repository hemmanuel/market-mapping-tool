import asyncio
import inspect
import socket
import uuid
from collections import Counter
from typing import Any, Dict

from src.orchestrator.core.ledger import OrchestrationLedger
from src.orchestrator.core.llm import BespokeLLMClient
from src.orchestrator.core.schemas import TaskFrame, TaskLease
from src.orchestrator.core.transitions import (
    TERMINAL_FAIL_RUN,
    TRANSITION_MODEL,
    materialize_route,
)
from src.orchestrator.workers.bouncer import BouncerWorker
from src.orchestrator.workers.canonical_persistence import PersistCanonicalEntitiesWorker
from src.orchestrator.workers.canonical_relationships import (
    CanonicalRelationshipAggregationWorker,
    PersistCanonicalRelationshipsWorker,
)
from src.orchestrator.workers.community_projection import (
    ProjectCommunitiesWorker,
    ProjectCommunitySummariesWorker,
)
from src.orchestrator.workers.canonical_resolution import CanonicalEntityResolutionWorker
from src.orchestrator.workers.enrichment import EnrichmentWorker
from src.orchestrator.workers.enrichment_persistence import (
    PersistCompanyEnrichmentWorker,
    ProjectCompanyEnrichmentWorker,
)
from src.orchestrator.workers.extraction import CompanyExtractionWorker
from src.orchestrator.workers.graph_barrier import GraphExtractionBarrierWorker
from src.orchestrator.workers.graph_documents import GraphDocumentSelectionWorker
from src.orchestrator.workers.graph_extraction import GraphFactExtractionWorker
from src.orchestrator.workers.graph_projection import (
    ProjectCanonicalEntitiesWorker,
    ProjectDocumentMentionsWorker,
    ProjectInteractsWithWorker,
    ProjectSemanticSimilarityWorker,
)
from src.orchestrator.workers.graph_publication import (
    PruneGraphWorker,
    PublishGraphReadyWorker,
)
from src.orchestrator.workers.global_dedup import GlobalDedupWorker
from src.orchestrator.workers.market_sizing import MarketSizingWorker
from src.orchestrator.workers.planner import PlannerWorker
from src.orchestrator.workers.scraper import ScraperWorker
from src.orchestrator.workers.search import SearchQueryWorker
from src.orchestrator.workers.vector_storage import VectorStorageWorker


class Orchestrator:
    GRAPH_STAGE_TOTAL = 12

    def __init__(self):
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4()}"
        self.ledger = OrchestrationLedger()
        self.llm_client = BespokeLLMClient()
        self.active_runs: dict[str, asyncio.Task] = {}
        self.site_run_index: dict[str, str] = {}
        self.max_parallel_tasks_per_run = 12
        self.poll_interval_seconds = 0.5
        self.max_parallel_tasks_per_class = {
            "llm": 4,
            "search": 4,
            "storage": 4,
            "scrape": 4,
            "embedding": 2,
            "cpu": 2,
            "graph_resolution": 1,
            "graph_projection": 1,
            None: 2,
        }
        self.lease_order = (
            "llm",
            "graph_resolution",
            "graph_projection",
            "search",
            "storage",
            "scrape",
            "embedding",
            "cpu",
            None,
        )

        self.workers = {
            "MARKET_SIZING": MarketSizingWorker(self.llm_client),
            "EXTRACT_COMPANIES": CompanyExtractionWorker(self.llm_client),
            "ENRICH_COMPANY": EnrichmentWorker(),
            "PERSIST_COMPANY_ENRICHMENT": PersistCompanyEnrichmentWorker(),
            "PROJECT_COMPANY_ENRICHMENT": ProjectCompanyEnrichmentWorker(),
            "PLAN_COMPANY_SEARCH": PlannerWorker(self.llm_client),
            "SEARCH_QUERY": SearchQueryWorker(),
            "GLOBAL_DEDUP_URL": GlobalDedupWorker(),
            "SCRAPE_URL": ScraperWorker(),
            "BOUNCER_EVALUATION": BouncerWorker(),
            "VECTOR_STORAGE": VectorStorageWorker(),
            "GRAPH_DOCUMENT_SELECTION": GraphDocumentSelectionWorker(),
            "GRAPH_EXTRACTION_BARRIER": GraphExtractionBarrierWorker(),
            "GRAPH_FACT_EXTRACTION": GraphFactExtractionWorker(self.llm_client),
            "CANONICAL_ENTITY_RESOLUTION": CanonicalEntityResolutionWorker(),
            "PERSIST_CANONICAL_ENTITIES": PersistCanonicalEntitiesWorker(),
            "CANONICAL_RELATIONSHIP_AGGREGATION": CanonicalRelationshipAggregationWorker(),
            "PERSIST_CANONICAL_RELATIONSHIPS": PersistCanonicalRelationshipsWorker(),
            "PROJECT_CANONICAL_ENTITIES": ProjectCanonicalEntitiesWorker(),
            "PROJECT_DOCUMENT_MENTIONS": ProjectDocumentMentionsWorker(),
            "PROJECT_INTERACTS_WITH": ProjectInteractsWithWorker(),
            "PROJECT_SEMANTIC_SIMILARITY": ProjectSemanticSimilarityWorker(),
            "PROJECT_COMMUNITIES": ProjectCommunitiesWorker(),
            "PROJECT_COMMUNITY_SUMMARIES": ProjectCommunitySummariesWorker(self.llm_client),
            "PRUNE_GRAPH": PruneGraphWorker(),
            "PUBLISH_GRAPH_READY": PublishGraphReadyWorker(),
        }

        self.semaphores = {
            "llm": asyncio.Semaphore(5),
            "search": asyncio.Semaphore(8),
            "scrape": asyncio.Semaphore(8),
            "storage": asyncio.Semaphore(8),
            "embedding": asyncio.Semaphore(4),
            "cpu": asyncio.Semaphore(8),
            "graph_resolution": asyncio.Semaphore(1),
            "graph_projection": asyncio.Semaphore(1),
        }

    async def start_pipeline(self, pipeline_id: str, initial_task_type: str, payload: Dict[str, Any]) -> str:
        run_id = await self.ledger.create_run(
            site_id=pipeline_id,
            objective="acquire",
            context_json=payload,
        )

        await self.ledger.enqueue_task(
            TaskFrame(
                run_id=run_id,
                pipeline_id=pipeline_id,
                task_type=initial_task_type,
                payload={"niche": payload.get("niche")},
                priority=400,
                concurrency_class="llm",
                idempotency_key=f"seed:{initial_task_type}",
            )
        )

        await self.ledger.record_event(
            site_id=pipeline_id,
            run_id=run_id,
            event_type="run_queued",
            payload={"type": "status", "is_acquiring": True},
        )

        run_task = asyncio.create_task(self._run_loop(run_id, pipeline_id, objective="acquire"))
        self.active_runs[run_id] = run_task
        self.site_run_index[pipeline_id] = run_id
        return run_id

    async def start_graph_pipeline(self, pipeline_id: str, niche: str, ontology: Dict[str, Any] | None = None) -> str:
        ontology = ontology or {}
        context_payload = {
            "niche": niche,
            "schema_entities": ontology.get("entities", []),
            "schema_relationships": ontology.get("relationships", []),
        }
        run_id = await self.ledger.create_run(
            site_id=pipeline_id,
            objective="graph",
            context_json=context_payload,
        )

        await self.ledger.enqueue_task(
            TaskFrame(
                run_id=run_id,
                pipeline_id=pipeline_id,
                task_type="GRAPH_DOCUMENT_SELECTION",
                payload={
                    "site_id": pipeline_id,
                    "run_id": run_id,
                    "candidate_document_ids": [],
                },
                priority=150,
                concurrency_class="storage",
                idempotency_key="seed:GRAPH_DOCUMENT_SELECTION",
            )
        )

        await self.ledger.record_event(
            site_id=pipeline_id,
            run_id=run_id,
            event_type="graph_run_queued",
            payload={
                "type": "graph_progress",
                "processed_chunks": 0,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Queued",
                "message": "Graph generation queued.",
            },
        )

        run_task = asyncio.create_task(self._run_loop(run_id, pipeline_id, objective="graph"))
        self.active_runs[run_id] = run_task
        return run_id

    async def wait_for_run(self, run_id: str, cancel_event: asyncio.Event | None = None) -> str:
        while True:
            if cancel_event and cancel_event.is_set():
                await self.cancel_run(run_id)

            run_task = self.active_runs.get(run_id)
            if run_task and run_task.done():
                await asyncio.gather(run_task, return_exceptions=True)
                status = await self.ledger.get_run_status(run_id)
                return status or "missing"

            status = await self.ledger.get_run_status(run_id)
            if status in {"completed", "cancelled", "failed"}:
                return status
            await asyncio.sleep(1)

    async def cancel_pipeline(self, pipeline_id: str) -> None:
        run_id = self.site_run_index.get(pipeline_id)
        if run_id:
            await self.cancel_run(run_id)

    async def cancel_run(self, run_id: str) -> None:
        await self.ledger.request_cancel(run_id)

    async def _run_loop(self, run_id: str, pipeline_id: str, objective: str) -> None:
        await self.ledger.mark_run_started(run_id)
        await self.ledger.record_event(
            site_id=pipeline_id,
            run_id=run_id,
            event_type="run_started",
            payload={"type": "log", "message": f"[Orchestrator] Run {run_id} started."},
        )
        if objective == "graph":
            await self.ledger.record_event(
                site_id=pipeline_id,
                run_id=run_id,
                event_type="graph_run_started",
                payload={
                    "type": "graph_progress",
                    "processed_chunks": 0,
                    "total_chunks": self.GRAPH_STAGE_TOTAL,
                    "current_phase": "Initialization",
                    "message": "Graph generation started.",
                },
            )

        inflight: set[asyncio.Task] = set()
        inflight_classes: dict[asyncio.Task, str | None] = {}
        try:
            while True:
                run_status = await self.ledger.get_run_status(run_id)
                stop_leasing = run_status in {"cancelling", "failed", "cancelled", "completed"}

                while len(inflight) < self.max_parallel_tasks_per_run and not stop_leasing:
                    inflight_counts = Counter(inflight_classes.values())
                    lease = await self._lease_next_available_task(run_id, inflight_counts)
                    if not lease:
                        break

                    await self.ledger.record_event(
                        site_id=pipeline_id,
                        run_id=run_id,
                        task_frame_id=lease.task.task_id,
                        event_type="task_leased",
                        payload={"type": "log", "message": f"[Orchestrator] Leased {lease.task.task_type} ({lease.task.task_id})."},
                    )
                    background_task = asyncio.create_task(self._process_task(lease, objective=objective))
                    inflight.add(background_task)
                    inflight_classes[background_task] = lease.task.concurrency_class
                    background_task.add_done_callback(inflight.discard)
                    background_task.add_done_callback(lambda finished: inflight_classes.pop(finished, None))

                if not inflight:
                    if stop_leasing or not await self.ledger.has_incomplete_tasks(run_id):
                        break
                    await asyncio.sleep(self.poll_interval_seconds)
                    continue

                await asyncio.wait(inflight, timeout=self.poll_interval_seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            final_status = await self.ledger.finalize_run(run_id)
            await self.ledger.record_event(
                site_id=pipeline_id,
                run_id=run_id,
                event_type="run_finished",
                payload={"type": "log", "message": f"[Orchestrator] Run {run_id} finished with status: {final_status}."},
            )
            if objective == "graph":
                terminal_payload = self._graph_terminal_payload(final_status)
                if terminal_payload:
                    await self.ledger.record_event(
                        site_id=pipeline_id,
                        run_id=run_id,
                        event_type="graph_run_status",
                        payload=terminal_payload,
                    )
            else:
                await self.ledger.record_event(
                    site_id=pipeline_id,
                    run_id=run_id,
                    event_type="run_status",
                    payload={"type": "status", "is_acquiring": False},
                )
            self.active_runs.pop(run_id, None)
            if self.site_run_index.get(pipeline_id) == run_id:
                self.site_run_index.pop(pipeline_id, None)

    async def _lease_next_available_task(self, run_id: str, inflight_counts: Counter[str | None]) -> TaskLease | None:
        for concurrency_class in self.lease_order:
            limit = self.max_parallel_tasks_per_class.get(concurrency_class, 1)
            if inflight_counts.get(concurrency_class, 0) >= limit:
                continue

            lease = await self.ledger.lease_next_task(
                run_id,
                self.worker_id,
                concurrency_class=concurrency_class,
                restrict_to_class=True,
            )
            if lease:
                return lease
        return None

    async def _process_task(self, lease: TaskLease, objective: str) -> None:
        task = lease.task
        worker = self.workers.get(task.task_type)
        if not worker:
            await self.ledger.fail_task(
                task_id=task.task_id,
                attempt_id=lease.attempt_id,
                error_code="UNKNOWN_TASK_TYPE",
                error_payload={"message": f"Unknown task type: {task.task_type}"},
                retryable=False,
            )
            return

        try:
            output = await self._execute_with_concurrency(task, worker, lease.attempt_id)
            output_payload = output.model_dump() if hasattr(output, "model_dump") else output
            outcome = self._determine_outcome(task.task_type, output_payload)
            artifacts = self._build_artifacts(task, output_payload)

            await self.ledger.complete_task(
                task_id=task.task_id,
                attempt_id=lease.attempt_id,
                outcome=outcome,
                output_payload=output_payload,
                artifacts=artifacts,
            )

            await self.ledger.record_event(
                site_id=task.pipeline_id,
                run_id=task.run_id,
                task_frame_id=task.task_id,
                event_type="task_completed",
                payload={"type": "log", "message": f"[Orchestrator] Completed {task.task_type} with outcome {outcome}."},
            )
            if objective == "graph":
                graph_progress_payload = self._build_graph_progress_payload(task.task_type, outcome, output_payload)
                if graph_progress_payload:
                    await self.ledger.record_event(
                        site_id=task.pipeline_id,
                        run_id=task.run_id,
                        task_frame_id=task.task_id,
                        event_type="graph_progress",
                        payload=graph_progress_payload,
                    )
                    if task.task_type == "PUBLISH_GRAPH_READY":
                        await self.ledger.record_event(
                            site_id=task.pipeline_id,
                            run_id=task.run_id,
                            task_frame_id=task.task_id,
                            event_type="graph_ready",
                            payload=graph_progress_payload,
                        )

            transition_spec = TRANSITION_MODEL.get(task.task_type)
            if not transition_spec:
                return

            route = transition_spec.routes.get(outcome)
            if not route:
                return

            context = await self.ledger.get_context(task.run_id)
            next_tasks = materialize_route(
                route,
                run_id=task.run_id,
                pipeline_id=task.pipeline_id,
                context=context,
                task=task,
                output=output_payload,
            )
            if next_tasks:
                await self.ledger.enqueue_tasks(next_tasks)
                await self.ledger.record_event(
                    site_id=task.pipeline_id,
                    run_id=task.run_id,
                    task_frame_id=task.task_id,
                    event_type="tasks_emitted",
                    payload={"type": "log", "message": f"[Orchestrator] Emitted {len(next_tasks)} downstream task(s) from {task.task_type}."},
                )

            if route.terminal_action == TERMINAL_FAIL_RUN:
                await self.ledger.mark_run_failed(task.run_id)
        except Exception as exc:
            result = await self.ledger.fail_task(
                task_id=task.task_id,
                attempt_id=lease.attempt_id,
                error_code=exc.__class__.__name__,
                error_payload={"message": str(exc)},
            )
            await self.ledger.record_event(
                site_id=task.pipeline_id,
                run_id=task.run_id,
                task_frame_id=task.task_id,
                event_type="task_failed",
                payload={"type": "log", "message": f"[Orchestrator] {task.task_type} failed: {exc} ({result})."},
            )
            if objective == "graph":
                await self.ledger.record_event(
                    site_id=task.pipeline_id,
                    run_id=task.run_id,
                    task_frame_id=task.task_id,
                    event_type="graph_progress",
                    payload={
                        "type": "graph_progress",
                        "processed_chunks": 0,
                        "total_chunks": self.GRAPH_STAGE_TOTAL,
                        "current_phase": "Error",
                        "message": f"Graph generation failed during {task.task_type}: {exc}",
                    },
                )

    async def _execute_with_concurrency(self, task: TaskFrame, worker: Any, attempt_id: str) -> Any:
        semaphore = self.semaphores.get(task.concurrency_class or "")
        if semaphore:
            async with semaphore:
                return await self._invoke_worker(worker, task, attempt_id)
        return await self._invoke_worker(worker, task, attempt_id)

    async def _invoke_worker(self, worker: Any, task: TaskFrame, attempt_id: str) -> Any:
        if getattr(worker, "accepts_attempt_id", False):
            return await worker.execute(task, attempt_id=attempt_id)

        execute_signature = inspect.signature(worker.execute)
        if "attempt_id" in execute_signature.parameters:
            return await worker.execute(task, attempt_id=attempt_id)

        return await worker.execute(task)

    def _determine_outcome(self, task_type: str, output_payload: dict[str, Any]) -> str:
        if task_type == "GLOBAL_DEDUP_URL":
            return "SCRAPE_REQUIRED" if output_payload.get("should_enqueue_scrape") else "CACHE_HIT"
        if task_type == "SCRAPE_URL":
            return "SUCCESS" if output_payload.get("raw_text") else "EMPTY"
        if task_type == "BOUNCER_EVALUATION":
            return "IS_RELEVANT" if output_payload.get("is_relevant") else "NOT_RELEVANT"
        if task_type == "ENRICH_COMPANY":
            return str(output_payload.get("status") or "SUCCESS")
        if task_type == "PERSIST_COMPANY_ENRICHMENT":
            return "SUCCESS" if output_payload.get("persisted") else "SKIPPED"
        if task_type == "GRAPH_EXTRACTION_BARRIER":
            return "SUCCESS" if output_payload.get("ready") else "WAITING"
        return "SUCCESS"

    def _build_graph_progress_payload(
        self,
        task_type: str,
        outcome: str,
        output_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if task_type == "GRAPH_DOCUMENT_SELECTION":
            document_count = len(output_payload.get("documents", []))
            return {
                "type": "graph_progress",
                "processed_chunks": 1,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 1: Document Selection",
                "message": f"Selected {document_count} document chunk(s) for graph extraction.",
            }

        if task_type == "GRAPH_EXTRACTION_BARRIER":
            document_count = int(output_payload.get("document_count", 0) or 0)
            pending_count = int(output_payload.get("pending_count", 0) or 0)
            completed_count = max(document_count - pending_count, 0)
            if outcome == "WAITING":
                return {
                    "type": "graph_progress",
                    "processed_chunks": 1,
                    "total_chunks": self.GRAPH_STAGE_TOTAL,
                    "current_phase": "Stage 2: Raw Fact Extraction",
                    "message": f"Extracted graph facts for {completed_count}/{document_count} document chunk(s).",
                }
            return {
                "type": "graph_progress",
                "processed_chunks": 2,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 2: Raw Fact Extraction",
                "message": f"Completed raw graph extraction for {document_count} document chunk(s).",
            }

        if task_type == "CANONICAL_ENTITY_RESOLUTION":
            canonical_count = len(output_payload.get("canonical_entities", []))
            return {
                "type": "graph_progress",
                "processed_chunks": 3,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 3: Canonical Entity Resolution",
                "message": f"Resolved {canonical_count} canonical entity cluster(s).",
            }

        if task_type == "CANONICAL_RELATIONSHIP_AGGREGATION":
            relationship_count = len(output_payload.get("canonical_relationships", []))
            return {
                "type": "graph_progress",
                "processed_chunks": 4,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 4: Relationship Aggregation",
                "message": f"Aggregated {relationship_count} canonical relationship(s).",
            }

        if task_type == "PROJECT_CANONICAL_ENTITIES":
            return {
                "type": "graph_progress",
                "processed_chunks": 5,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 5: Canonical Projection",
                "message": f"Projected {int(output_payload.get('projected_entities', 0) or 0)} canonical entity node(s).",
            }

        if task_type == "PROJECT_DOCUMENT_MENTIONS":
            return {
                "type": "graph_progress",
                "processed_chunks": 6,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 6: Document Projection",
                "message": (
                    "Projected "
                    f"{int(output_payload.get('projected_documents', 0) or 0)} document node(s) and "
                    f"{int(output_payload.get('projected_mentions', 0) or 0)} mention edge(s)."
                ),
            }

        if task_type == "PROJECT_INTERACTS_WITH":
            return {
                "type": "graph_progress",
                "processed_chunks": 7,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 7: Relationship Projection",
                "message": f"Projected {int(output_payload.get('projected_relationships', 0) or 0)} INTERACTS_WITH edge(s).",
            }

        if task_type == "PROJECT_SEMANTIC_SIMILARITY":
            return {
                "type": "graph_progress",
                "processed_chunks": 8,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 8: Semantic Similarity",
                "message": (
                    "Projected "
                    f"{int(output_payload.get('projected_similarity_edges', 0) or 0)} SIMILAR_TO edge(s)."
                ),
            }

        if task_type == "PROJECT_COMMUNITIES":
            return {
                "type": "graph_progress",
                "processed_chunks": 9,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 9: Community Detection",
                "message": (
                    "Projected "
                    f"{int(output_payload.get('projected_communities', 0) or 0)} communit(y/ies) and "
                    f"{int(output_payload.get('projected_memberships', 0) or 0)} community membership edge(s)."
                ),
            }

        if task_type == "PROJECT_COMMUNITY_SUMMARIES":
            return {
                "type": "graph_progress",
                "processed_chunks": 10,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 10: Community Summaries",
                "message": (
                    "Generated summaries for "
                    f"{int(output_payload.get('summarized_communities', 0) or 0)} communit(y/ies)."
                ),
            }

        if task_type == "PRUNE_GRAPH":
            return {
                "type": "graph_progress",
                "processed_chunks": 11,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Stage 11: Graph Pruning",
                "message": (
                    "Removed "
                    f"{int(output_payload.get('deleted_entities', 0) or 0)} stale canonical entit(y/ies), "
                    f"{int(output_payload.get('deleted_documents', 0) or 0)} stale document node(s), and "
                    f"{int(output_payload.get('deleted_mentions', 0) or 0)} stale mention edge(s)."
                ),
            }

        if task_type == "PUBLISH_GRAPH_READY":
            return {
                "type": "graph_progress",
                "processed_chunks": 12,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Graph Ready",
                "message": (
                    "Verified graph projection with "
                    f"{int(output_payload.get('canonical_entity_count', 0) or 0)} canonical entit(y/ies), "
                    f"{int(output_payload.get('document_count', 0) or 0)} document node(s), "
                    f"{int(output_payload.get('mention_count', 0) or 0)} mention edge(s), and "
                    f"{int(output_payload.get('relationship_count', 0) or 0)} INTERACTS_WITH edge(s), "
                    f"{int(output_payload.get('similarity_edge_count', 0) or 0)} SIMILAR_TO edge(s), "
                    f"{int(output_payload.get('community_count', 0) or 0)} communit(y/ies), and "
                    f"{int(output_payload.get('community_membership_count', 0) or 0)} BELONGS_TO edge(s)."
                ),
            }

        return None

    def _graph_terminal_payload(self, final_status: str) -> dict[str, Any] | None:
        if final_status == "completed":
            return {
                "type": "graph_progress",
                "processed_chunks": self.GRAPH_STAGE_TOTAL,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Complete",
                "message": "Graph generation completed successfully.",
            }
        if final_status == "cancelled":
            return {
                "type": "graph_progress",
                "processed_chunks": 0,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Cancelled",
                "message": "Graph generation was cancelled.",
            }
        if final_status == "failed":
            return {
                "type": "graph_progress",
                "processed_chunks": 0,
                "total_chunks": self.GRAPH_STAGE_TOTAL,
                "current_phase": "Error",
                "message": "Graph generation failed.",
            }
        return None

    def _build_artifacts(self, task: TaskFrame, output_payload: dict[str, Any]) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        if task.task_type == "SCRAPE_URL" and output_payload.get("storage_object"):
            artifacts.append(
                {
                    "artifact_type": "source_object",
                    "artifact_key": output_payload["storage_object"],
                    "metadata_json": {
                        "source_url": task.payload.get("url"),
                        "status_code": output_payload.get("status_code"),
                    },
                }
            )
        if task.task_type == "VECTOR_STORAGE":
            artifacts.append(
                {
                    "artifact_type": "vectorized_document",
                    "artifact_key": task.payload.get("url"),
                    "metadata_json": {
                        "stored_chunks": output_payload.get("stored_chunks", 0),
                        "company_name": task.payload.get("company_name"),
                        "document_ids": output_payload.get("document_ids", []),
                    },
                }
            )
        if task.task_type == "GRAPH_FACT_EXTRACTION":
            document = task.payload.get("document") or {}
            artifacts.append(
                {
                    "artifact_type": "graph_fact_batch",
                    "artifact_key": document.get("document_id") or task.task_id,
                    "metadata_json": {
                        "document_id": document.get("document_id"),
                        "entity_fact_count": len(output_payload.get("entity_fact_ids", [])),
                        "relationship_fact_count": len(output_payload.get("relationship_fact_ids", [])),
                    },
                }
            )
        if task.task_type == "ENRICH_COMPANY":
            company_profile = output_payload.get("company_profile") or {}
            if company_profile:
                vc_dossier = company_profile.get("vc_dossier") or {}
                founders = company_profile.get("founders") or []
                artifact_key = (
                    company_profile.get("company_name")
                    or company_profile.get("name")
                    or task.payload.get("company_name")
                    or task.task_id
                )
                artifacts.append(
                    {
                        "artifact_type": "company_enrichment_profile",
                        "artifact_key": artifact_key,
                        "metadata_json": {
                            "company_name": company_profile.get("company_name") or company_profile.get("name"),
                            "stage_estimate": company_profile.get("stage_estimate"),
                            "venture_scale_score": company_profile.get("venture_scale_score"),
                            "primary_sector": company_profile.get("primary_sector"),
                            "source_urls": vc_dossier.get("source_urls", []),
                            "source_document_ids": output_payload.get("source_document_ids", []),
                            "document_count": output_payload.get("document_count", 0),
                            "founder_count": len(founders),
                            "company_profile": company_profile,
                        },
                    }
                )
        if task.task_type == "PERSIST_COMPANY_ENRICHMENT" and output_payload.get("persisted"):
            artifacts.append(
                {
                    "artifact_type": "normalized_company_enrichment",
                    "artifact_key": output_payload.get("company_enrichment_id") or task.task_id,
                    "metadata_json": {
                        "company_enrichment_id": output_payload.get("company_enrichment_id"),
                        "company_name": output_payload.get("company_name"),
                        "founder_count": len(output_payload.get("founder_ids", [])),
                    },
                }
            )
        if task.task_type == "PROJECT_COMPANY_ENRICHMENT" and output_payload.get("projected"):
            artifacts.append(
                {
                    "artifact_type": "neo4j_company_enrichment_projection",
                    "artifact_key": output_payload.get("company_name") or task.task_id,
                    "metadata_json": {
                        "company_name": output_payload.get("company_name"),
                        "projected_companies": output_payload.get("projected_companies", 0),
                        "projected_founders": output_payload.get("projected_founders", 0),
                    },
                }
            )
        if task.task_type == "PERSIST_CANONICAL_ENTITIES":
            artifacts.append(
                {
                    "artifact_type": "canonical_entity_batch",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "canonical_entity_count": len(output_payload.get("canonical_entity_ids", [])),
                        "membership_count": len(output_payload.get("membership_ids", [])),
                    },
                }
            )
        if task.task_type == "PERSIST_CANONICAL_RELATIONSHIPS":
            artifacts.append(
                {
                    "artifact_type": "canonical_relationship_batch",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "canonical_relationship_count": len(output_payload.get("canonical_relationship_ids", [])),
                    },
                }
            )
        if task.task_type == "PROJECT_CANONICAL_ENTITIES":
            artifacts.append(
                {
                    "artifact_type": "neo4j_canonical_projection",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "projected_entities": output_payload.get("projected_entities", 0),
                    },
                }
            )
        if task.task_type == "PROJECT_DOCUMENT_MENTIONS":
            artifacts.append(
                {
                    "artifact_type": "neo4j_document_mentions_projection",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "projected_documents": output_payload.get("projected_documents", 0),
                        "projected_mentions": output_payload.get("projected_mentions", 0),
                    },
                }
            )
        if task.task_type == "PROJECT_INTERACTS_WITH":
            artifacts.append(
                {
                    "artifact_type": "neo4j_interacts_with_projection",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "projected_relationships": output_payload.get("projected_relationships", 0),
                    },
                }
            )
        if task.task_type == "PROJECT_SEMANTIC_SIMILARITY":
            artifacts.append(
                {
                    "artifact_type": "neo4j_semantic_similarity_projection",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "projected_similarity_edges": output_payload.get("projected_similarity_edges", 0),
                    },
                }
            )
        if task.task_type == "PROJECT_COMMUNITIES":
            artifacts.append(
                {
                    "artifact_type": "neo4j_community_projection",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "projected_communities": output_payload.get("projected_communities", 0),
                        "projected_memberships": output_payload.get("projected_memberships", 0),
                    },
                }
            )
        if task.task_type == "PROJECT_COMMUNITY_SUMMARIES":
            artifacts.append(
                {
                    "artifact_type": "neo4j_community_summary_projection",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "summarized_communities": output_payload.get("summarized_communities", 0),
                    },
                }
            )
        if task.task_type == "PRUNE_GRAPH":
            artifacts.append(
                {
                    "artifact_type": "neo4j_graph_prune",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "deleted_documents": output_payload.get("deleted_documents", 0),
                        "deleted_entities": output_payload.get("deleted_entities", 0),
                        "deleted_mentions": output_payload.get("deleted_mentions", 0),
                    },
                }
            )
        if task.task_type == "PUBLISH_GRAPH_READY":
            artifacts.append(
                {
                    "artifact_type": "graph_ready_publication",
                    "artifact_key": task.task_id,
                    "metadata_json": {
                        "graph_status": output_payload.get("graph_status"),
                        "canonical_entity_count": output_payload.get("canonical_entity_count", 0),
                        "document_count": output_payload.get("document_count", 0),
                        "mention_count": output_payload.get("mention_count", 0),
                        "relationship_count": output_payload.get("relationship_count", 0),
                        "similarity_edge_count": output_payload.get("similarity_edge_count", 0),
                        "community_count": output_payload.get("community_count", 0),
                        "community_membership_count": output_payload.get("community_membership_count", 0),
                    },
                }
            )
        return artifacts
