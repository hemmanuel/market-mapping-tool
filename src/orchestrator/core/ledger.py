import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_, select, update

from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.orchestrator.core.ledger_models import (
    DeadLetterTask,
    OrchestrationTaskFrameRecord,
    OutboxEvent,
    PipelineRun,
    TaskArtifact,
    TaskAttempt,
    WorkflowContext,
)
from src.orchestrator.core.persistence_keys import (
    ARTIFACT_KEY_MAX_LENGTH,
    PARTITION_KEY_MAX_LENGTH,
    TASK_FRAME_KEY_MAX_LENGTH,
    normalize_persistence_key,
)
from src.orchestrator.core.schemas import TaskFrame, TaskLease


TERMINAL_TASK_STATUSES = {"completed", "cancelled", "discarded", "dead_lettered"}
ACTIVE_TASK_STATUSES = {"pending", "in_progress"}
TERMINAL_RUN_STATUSES = {"completed", "cancelled", "failed"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_uuid(value: str | uuid.UUID | None) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _sanitize_string(value: str) -> str:
    return value.replace("\x00", "")


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_json_value(item) for key, item in value.items()}
    return value


class OrchestrationLedger:
    async def create_run(self, site_id: str, objective: str, context_json: dict[str, Any], orchestration_version: str = "bespoke-v2") -> str:
        async with AsyncSessionLocal() as session:
            run = PipelineRun(
                site_id=to_uuid(site_id),
                status="queued",
                objective=objective,
                orchestration_version=orchestration_version,
            )
            session.add(run)
            await session.flush()

            workflow_context = WorkflowContext(
                run_id=run.id,
                site_id=run.site_id,
                schema_version="1",
                context_json=_sanitize_json_value(context_json),
            )
            session.add(workflow_context)
            await session.commit()

        await self.record_event(
            site_id=site_id,
            run_id=str(run.id),
            event_type="run_created",
            payload={"type": "log", "message": f"[Orchestrator] Created run {run.id} for site {site_id}."},
        )
        return str(run.id)

    async def mark_run_started(self, run_id: str) -> None:
        async with AsyncSessionLocal() as session:
            run = await session.get(PipelineRun, to_uuid(run_id))
            if not run:
                return
            if run.status == "queued":
                run.status = "running"
                run.started_at = run.started_at or utcnow()
                await session.commit()

    async def request_cancel(self, run_id: str) -> None:
        async with AsyncSessionLocal() as session:
            run = await session.get(PipelineRun, to_uuid(run_id))
            if not run or run.status in TERMINAL_RUN_STATUSES:
                return
            run.status = "cancelling"
            await session.commit()

    async def mark_run_failed(self, run_id: str) -> None:
        async with AsyncSessionLocal() as session:
            run = await session.get(PipelineRun, to_uuid(run_id))
            if not run:
                return
            run.status = "failed"
            run.completed_at = utcnow()
            await session.commit()

    async def is_cancel_requested(self, run_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            run = await session.get(PipelineRun, to_uuid(run_id))
            return bool(run and run.status == "cancelling")

    async def finalize_run(self, run_id: str) -> str:
        async with AsyncSessionLocal() as session:
            run = await session.get(PipelineRun, to_uuid(run_id))
            if not run:
                return "missing"

            dead_letter_count = await session.scalar(
                select(func.count()).select_from(DeadLetterTask).where(DeadLetterTask.run_id == run.id)
            )
            if run.status == "failed":
                run.completed_at = run.completed_at or utcnow()
            elif run.status == "cancelling":
                run.status = "cancelled"
                run.cancelled_at = utcnow()
                run.completed_at = run.completed_at or utcnow()
            elif dead_letter_count and dead_letter_count > 0:
                run.status = "failed"
                run.completed_at = run.completed_at or utcnow()
            else:
                run.status = "completed"
                run.completed_at = utcnow()

            if run.status in {"cancelled", "failed"}:
                await session.execute(
                    update(OrchestrationTaskFrameRecord)
                    .where(
                        OrchestrationTaskFrameRecord.run_id == run.id,
                        ~OrchestrationTaskFrameRecord.status.in_(TERMINAL_TASK_STATUSES),
                    )
                    .values(
                        status="cancelled",
                        completed_at=utcnow(),
                        lease_owner=None,
                        lease_expires_at=None,
                    )
                )
            await session.commit()
            return run.status

    async def get_run_status(self, run_id: str) -> Optional[str]:
        async with AsyncSessionLocal() as session:
            run = await session.get(PipelineRun, to_uuid(run_id))
            return run.status if run else None

    async def has_incomplete_tasks(self, run_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(OrchestrationTaskFrameRecord)
                .where(
                    OrchestrationTaskFrameRecord.run_id == to_uuid(run_id),
                    ~OrchestrationTaskFrameRecord.status.in_(TERMINAL_TASK_STATUSES),
                )
            )
            return bool(count and count > 0)

    async def get_context(self, run_id: str) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(WorkflowContext).where(WorkflowContext.run_id == to_uuid(run_id)).limit(1)
            )
            workflow_context = result.scalars().first()
            return workflow_context.context_json if workflow_context else {}

    async def enqueue_task(self, task: TaskFrame) -> TaskFrame:
        async with AsyncSessionLocal() as session:
            persisted_dedupe_key = normalize_persistence_key(
                task.dedupe_key,
                max_length=TASK_FRAME_KEY_MAX_LENGTH,
            )
            persisted_idempotency_key = normalize_persistence_key(
                task.idempotency_key,
                max_length=TASK_FRAME_KEY_MAX_LENGTH,
            )
            persisted_partition_key = normalize_persistence_key(
                task.partition_key,
                max_length=PARTITION_KEY_MAX_LENGTH,
            )
            existing = None
            if persisted_idempotency_key:
                result = await session.execute(
                    select(OrchestrationTaskFrameRecord)
                    .where(
                        OrchestrationTaskFrameRecord.run_id == to_uuid(task.run_id),
                        OrchestrationTaskFrameRecord.task_type == task.task_type,
                        OrchestrationTaskFrameRecord.idempotency_key == persisted_idempotency_key,
                    )
                    .limit(1)
                )
                existing = result.scalars().first()

            if existing:
                return self._to_task_frame(existing)

            task_id = to_uuid(task.task_id) or uuid.uuid4()
            root_task_id = to_uuid(task.root_task_id) or task_id

            record = OrchestrationTaskFrameRecord(
                id=task_id,
                run_id=to_uuid(task.run_id),
                site_id=to_uuid(task.pipeline_id),
                parent_task_id=to_uuid(task.parent_task_id),
                root_task_id=root_task_id,
                task_type=task.task_type,
                payload_json=_sanitize_json_value(task.payload),
                payload_schema_version=task.payload_schema_version,
                worker_version=task.worker_version,
                priority=task.priority,
                partition_key=persisted_partition_key,
                concurrency_class=task.concurrency_class,
                dedupe_key=persisted_dedupe_key,
                idempotency_key=persisted_idempotency_key,
                status="pending",
                attempt_count=task.retry_count,
                max_attempts=task.max_retries,
                scheduled_at=task.scheduled_at or utcnow(),
                available_at=task.available_at or utcnow(),
            )
            session.add(record)
            await session.commit()
            return self._to_task_frame(record)

    async def enqueue_tasks(self, tasks: Iterable[TaskFrame]) -> list[TaskFrame]:
        enqueued: list[TaskFrame] = []
        for task in tasks:
            enqueued.append(await self.enqueue_task(task))
        return enqueued

    async def lease_next_task(
        self,
        run_id: str,
        worker_id: str,
        lease_seconds: int = 120,
        concurrency_class: str | None = None,
        restrict_to_class: bool = False,
    ) -> Optional[TaskLease]:
        async with AsyncSessionLocal() as session:
            now = utcnow()
            conditions = [
                OrchestrationTaskFrameRecord.run_id == to_uuid(run_id),
                OrchestrationTaskFrameRecord.status == "pending",
                OrchestrationTaskFrameRecord.available_at <= now,
                or_(
                    OrchestrationTaskFrameRecord.lease_expires_at.is_(None),
                    OrchestrationTaskFrameRecord.lease_expires_at <= now,
                ),
            ]
            if restrict_to_class:
                if concurrency_class is None:
                    conditions.append(OrchestrationTaskFrameRecord.concurrency_class.is_(None))
                else:
                    conditions.append(OrchestrationTaskFrameRecord.concurrency_class == concurrency_class)

            result = await session.execute(
                select(OrchestrationTaskFrameRecord)
                .where(*conditions)
                .order_by(
                    OrchestrationTaskFrameRecord.priority.asc(),
                    OrchestrationTaskFrameRecord.available_at.asc(),
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            record = result.scalars().first()
            if not record:
                return None

            record.status = "in_progress"
            record.attempt_count += 1
            record.started_at = record.started_at or now
            record.heartbeat_at = now
            record.lease_owner = worker_id
            record.lease_expires_at = now + timedelta(seconds=lease_seconds)

            attempt = TaskAttempt(
                task_frame_id=record.id,
                run_id=record.run_id,
                site_id=record.site_id,
                attempt_number=record.attempt_count,
                status="in_progress",
                worker_version=record.worker_version,
                lease_owner=worker_id,
                started_at=now,
                heartbeat_at=now,
            )
            session.add(attempt)
            await session.commit()
            return TaskLease(task=self._to_task_frame(record), attempt_id=str(attempt.id))

    async def heartbeat(self, task_id: str, attempt_id: str, worker_id: str, lease_seconds: int = 120) -> None:
        async with AsyncSessionLocal() as session:
            task = await session.get(OrchestrationTaskFrameRecord, to_uuid(task_id))
            attempt = await session.get(TaskAttempt, to_uuid(attempt_id))
            if not task or not attempt:
                return
            now = utcnow()
            task.heartbeat_at = now
            task.lease_owner = worker_id
            task.lease_expires_at = now + timedelta(seconds=lease_seconds)
            attempt.heartbeat_at = now
            await session.commit()

    async def complete_task(
        self,
        task_id: str,
        attempt_id: str,
        outcome: str,
        output_payload: dict[str, Any],
        artifacts: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            task = await session.get(OrchestrationTaskFrameRecord, to_uuid(task_id))
            attempt = await session.get(TaskAttempt, to_uuid(attempt_id))
            if not task or not attempt:
                return

            now = utcnow()
            task.status = "completed"
            task.outcome = outcome
            task.completed_at = now
            task.heartbeat_at = now
            task.lease_owner = None
            task.lease_expires_at = None

            attempt.status = "completed"
            attempt.outcome = outcome
            attempt.finished_at = now
            attempt.heartbeat_at = now
            attempt.output_json = _sanitize_json_value(output_payload)

            for artifact in artifacts or []:
                artifact_key = normalize_persistence_key(
                    artifact.get("artifact_key"),
                    max_length=ARTIFACT_KEY_MAX_LENGTH,
                ) or str(task.id)
                session.add(
                    TaskArtifact(
                        task_frame_id=task.id,
                        run_id=task.run_id,
                        site_id=task.site_id,
                        artifact_type=artifact["artifact_type"],
                        artifact_key=artifact_key,
                        uri=artifact.get("uri"),
                        metadata_json=_sanitize_json_value(artifact.get("metadata_json", {})),
                    )
                )

            await session.commit()

    async def fail_task(
        self,
        task_id: str,
        attempt_id: str,
        error_code: str,
        error_payload: dict[str, Any],
        retryable: bool = True,
    ) -> str:
        async with AsyncSessionLocal() as session:
            task = await session.get(OrchestrationTaskFrameRecord, to_uuid(task_id))
            attempt = await session.get(TaskAttempt, to_uuid(attempt_id))
            if not task or not attempt:
                return "missing"

            now = utcnow()
            task.last_error_code = error_code
            task.last_error_payload = _sanitize_json_value(error_payload)
            task.lease_owner = None
            task.lease_expires_at = None
            task.heartbeat_at = now

            attempt.status = "failed"
            attempt.error_code = error_code
            attempt.error_payload = _sanitize_json_value(error_payload)
            attempt.finished_at = now
            attempt.heartbeat_at = now

            if retryable and task.attempt_count < task.max_attempts:
                backoff_seconds = min(300, 2 ** task.attempt_count)
                task.status = "pending"
                task.available_at = now + timedelta(seconds=backoff_seconds)
                await session.commit()
                return "retry_scheduled"

            task.status = "dead_lettered"
            task.completed_at = now
            task.outcome = "FAILED"

            session.add(
                DeadLetterTask(
                    run_id=task.run_id,
                    site_id=task.site_id,
                    task_frame_id=task.id,
                    task_type=task.task_type,
                    payload_json=task.payload_json,
                    failure_reason=_sanitize_string(str(error_payload.get("message", ""))),
                    error_code=error_code,
                    error_payload=_sanitize_json_value(error_payload),
                    created_at=now,
                    last_attempt_at=now,
                )
            )
            await session.commit()
            return "dead_lettered"

    async def record_event(
        self,
        site_id: str,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        task_frame_id: Optional[str] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            event = OutboxEvent(
                run_id=to_uuid(run_id),
                site_id=to_uuid(site_id),
                task_frame_id=to_uuid(task_frame_id),
                event_type=event_type,
                payload_json=_sanitize_json_value(payload),
                status="published",
                published_at=utcnow(),
            )
            session.add(event)
            await session.commit()

        await event_manager.publish(site_id, payload)

    def _to_task_frame(self, record: OrchestrationTaskFrameRecord) -> TaskFrame:
        return TaskFrame(
            task_id=str(record.id),
            run_id=str(record.run_id),
            pipeline_id=str(record.site_id),
            parent_task_id=str(record.parent_task_id) if record.parent_task_id else None,
            root_task_id=str(record.root_task_id) if record.root_task_id else None,
            task_type=record.task_type,
            payload=record.payload_json,
            status=record.status,
            outcome=record.outcome,
            payload_schema_version=record.payload_schema_version,
            worker_version=record.worker_version,
            priority=record.priority,
            partition_key=record.partition_key,
            concurrency_class=record.concurrency_class,
            dedupe_key=record.dedupe_key,
            idempotency_key=record.idempotency_key,
            retry_count=record.attempt_count,
            max_retries=record.max_attempts,
            lease_owner=record.lease_owner,
            scheduled_at=record.scheduled_at,
            available_at=record.available_at,
            started_at=record.started_at,
            heartbeat_at=record.heartbeat_at,
            completed_at=record.completed_at,
        )
