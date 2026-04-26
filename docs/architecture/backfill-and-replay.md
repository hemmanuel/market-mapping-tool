# Backfill and Replay

## Rule

Backfill is not a separate ingestion system.

Replay is not an excuse to bypass durable acquisition.

## Backfill Model

Backfill an existing site by creating a new run against that site with an explicit objective, for example:

- recover early-stage startup coverage,
- re-acquire missing primary sources,
- rebuild graph projections from existing evidence,
- or rerun a failed acquisition stage.

## Replay Modes

### Full replay

Re-run discovery, planning, search, acquisition, storage, and projection for a site or scope.

### Partial replay

Replay only a subset of tasks, such as:

- search planning,
- scrape tasks,
- projection tasks.

### Projection rebuild

Rebuild Neo4j or other projections from already durable source state in Postgres and MinIO.

## Constraints

- A replay must preserve idempotency.
- A backfill must still respect front-door ingestion.
- Any direct-write shortcut that skips source acquisition or durable provenance is invalid.

## Operator Expectation

An operator should be able to answer:

- what run performed the backfill,
- what new evidence was acquired,
- what was reused,
- what failed,
- and what remains safe to replay.
