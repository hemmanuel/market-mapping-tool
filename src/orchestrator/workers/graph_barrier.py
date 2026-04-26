import uuid

from sqlalchemy import select

from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.orchestrator.core.graph_contracts import GraphExtractionBarrierInput, GraphExtractionBarrierOutput
from src.orchestrator.core.ledger_models import OrchestrationTaskFrameRecord
from src.orchestrator.core.schemas import TaskFrame


class GraphExtractionBarrierWorker:
    async def execute(self, task: TaskFrame) -> GraphExtractionBarrierOutput:
        payload = GraphExtractionBarrierInput(**task.payload)
        pipeline_id = task.pipeline_id
        selection_task_uuid = uuid.UUID(payload.selection_task_id)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OrchestrationTaskFrameRecord.status, OrchestrationTaskFrameRecord.outcome)
                .where(
                    OrchestrationTaskFrameRecord.run_id == uuid.UUID(payload.run_id),
                    OrchestrationTaskFrameRecord.parent_task_id == selection_task_uuid,
                    OrchestrationTaskFrameRecord.task_type == "GRAPH_FACT_EXTRACTION",
                )
            )
            rows = result.all()

        expected_count = len(payload.documents)
        task_count = len(rows)
        pending_count = sum(1 for row in rows if row.status in {"pending", "in_progress"})
        failed_count = sum(1 for row in rows if row.status in {"dead_lettered", "cancelled", "discarded"})
        unexpected_completed_count = sum(
            1 for row in rows if row.status == "completed" and row.outcome not in {None, "SUCCESS"}
        )
        completed_success_count = sum(
            1 for row in rows if row.status == "completed" and row.outcome == "SUCCESS"
        )

        if failed_count or unexpected_completed_count:
            raise RuntimeError(
                "Graph extraction barrier detected non-success extraction tasks "
                f"(failed={failed_count}, unexpected_completed={unexpected_completed_count}) "
                f"for selection {payload.selection_task_id}."
            )

        if task_count < expected_count or pending_count > 0:
            next_poll_count = payload.poll_count + 1
            await event_manager.publish(
                pipeline_id,
                {
                    "type": "log",
                    "message": (
                        "[GraphBarrier] Waiting for graph fact extraction tasks "
                        f"({completed_success_count}/{expected_count} ready, {pending_count} pending, poll {next_poll_count})."
                    ),
                },
            )
            return GraphExtractionBarrierOutput(
                ready=False,
                document_count=expected_count,
                pending_count=pending_count + max(expected_count - task_count, 0),
                failed_count=0,
                poll_count=next_poll_count,
            )

        await event_manager.publish(
            pipeline_id,
            {
                "type": "log",
                "message": (
                    f"[GraphBarrier] All {completed_success_count} graph extraction task(s) completed for selection "
                    f"{payload.selection_task_id}."
                ),
            },
        )
        return GraphExtractionBarrierOutput(
            ready=True,
            document_count=expected_count,
            pending_count=0,
            failed_count=0,
            poll_count=payload.poll_count,
        )
