# Task Frame Contract

## Role

A task frame is the durable envelope for one unit of work.

## Minimum Required Fields

- `task_id`
- `run_id`
- `pipeline_id`
- `task_type`
- `payload`
- `status`
- `attempt_count`
- `max_attempts`
- `idempotency_key`
- `dedupe_key`
- `scheduled_at`
- `available_at`
- `started_at`
- `completed_at`
- `lease_owner`
- `heartbeat_at`
- `worker_version`
- `payload_schema_version`

## Why This Matters

The current lightweight shape in code is only a starting point. A production task frame must support:

- replay,
- leasing,
- stuck-task recovery,
- deduplication,
- worker upgrades,
- and auditability.

## Rule

If a workflow guarantee depends on a field, that field belongs in the durable task model rather than in local memory.

Key fields are persistence contracts, not arbitrary text dumps. When raw
queries, URLs, or similar source values exceed fixed column limits, the task
frame should keep the raw value in `payload` and persist a stable bounded
fingerprint in `idempotency_key`, `dedupe_key`, or `partition_key`.
