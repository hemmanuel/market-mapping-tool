# Event Catalog

## Purpose

UI progress and operator visibility should be driven by durable event semantics, not only by ad hoc in-memory notifications.

## Current Event Families

The current branch already uses a mix of durable ledger-backed events and legacy UI event families.

Durable or orchestrator-owned event families now include run and task lifecycle events such as:

- run created,
- run started,
- run completed or failed,
- task leased,
- task completed or failed,
- follow-on task emission records,
- bespoke graph-stage updates published as durable `graph_progress` events,
- and a durable `graph_ready` publication event once projection verification succeeds.

Worker and UI-facing event families still in use include:

- `log`
- `status`
- `graph_progress`
- `queue`
- `queue_update`
- `new_chunk`
- `large_file_pending`

## Target Event Model

The kernel should emit durable events for at least:

- run created
- run started
- run completed
- run failed
- task leased
- task heartbeat
- task completed
- task failed
- task dead-lettered
- source acquired
- source rejected
- chunk batch stored
- projection started
- projection updated
- projection completed
- projection failed
- graph ready

## Rule

Event definitions must converge on the outbox model so UI progress survives process failures and can be replayed or projected reliably.

The remaining gap is not whether graph progress or graph readiness exist on the bespoke path, but how far we push them: replay-friendly read models and the last legacy UI event families still need to converge on the same durable projection model.
