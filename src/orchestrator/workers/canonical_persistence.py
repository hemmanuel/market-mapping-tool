from src.api.events import event_manager
from src.db.session import AsyncSessionLocal
from src.orchestrator.core.graph_contracts import (
    CanonicalEntityResolutionOutput,
    PersistCanonicalEntitiesInput,
    PersistCanonicalEntitiesResult,
)
from src.orchestrator.core.graph_store import persist_canonical_entity_resolution
from src.orchestrator.core.schemas import TaskFrame


class PersistCanonicalEntitiesWorker:
    accepts_attempt_id = True

    async def execute(self, task: TaskFrame, attempt_id: str | None = None) -> PersistCanonicalEntitiesResult:
        if not attempt_id:
            raise RuntimeError("PersistCanonicalEntitiesWorker requires a task attempt id for durable lineage.")

        payload = PersistCanonicalEntitiesInput(**task.payload)
        resolution_output = CanonicalEntityResolutionOutput(
            canonical_entities=payload.canonical_entities,
            memberships=payload.memberships,
        )

        async with AsyncSessionLocal() as session:
            persisted = await persist_canonical_entity_resolution(
                session,
                run_id=payload.run_id,
                site_id=payload.site_id,
                task_frame_id=task.task_id,
                task_attempt_id=attempt_id,
                output=resolution_output,
            )
            await session.commit()

        await event_manager.publish(
            task.pipeline_id,
            {
                "type": "log",
                "message": (
                    "[CanonicalPersistence] Persisted "
                    f"{len(persisted.canonical_entity_ids)} canonical entit(y/ies) and "
                    f"{len(persisted.membership_ids)} membership(s)."
                ),
            },
        )
        return persisted
