# Migration Governance

## Goal

Migrate from the legacy LangGraph runtime to the bespoke orchestration kernel without degrading acquisition quality, source preservation, observability, or user-facing behavior.

## Governing Rule

The new runtime must not be considered complete because it compiles or runs once. It becomes the production architecture only after it meets parity and durability criteria.

## Mandatory Gates

### Gate 1: Documentation completeness

Before major kernel expansion:

- philosophy docs must be current,
- architectural invariants must be written,
- and ADRs for core decisions must exist.

### Gate 2: Durable orchestration model

Before cutover:

- workflow state must be durable,
- retries must be explicit,
- replay must be supported,
- and dead-letter handling must exist.

### Gate 3: Front-door parity

The bespoke kernel must support the same end-to-end acquisition responsibilities as the legacy flow:

- discovery,
- query planning,
- URL/source resolution,
- acquisition,
- source preservation,
- chunking,
- embedding,
- graph projection,
- and UI progress updates.

### Gate 4: Shadow-mode verification

The new kernel must run alongside the old flow on representative sites and prove parity or improvement on:

- discovered company count,
- source acquisition count,
- primary artifact preservation,
- chunk counts,
- embedding coverage,
- and graph projection quality.

### Gate 5: Cutover review

This branch may route acquisition requests through the bespoke runtime for verification, but the migration is not considered cut over until the earlier gates are satisfied for both acquisition and graph projection.

## Temporary vs Permanent

- `.cursor/plans/` may describe ideas and workstreams.
- `docs/` defines the architecture of record.
- code should follow `docs/`, not vice versa.

## Current Status

The bespoke kernel branch is now beyond the documentation-only and skeleton-runtime phases.

### Completed on this branch

- the durable orchestration ledger exists in PostgreSQL,
- the declarative transition model is implemented for bespoke acquisition and the current bespoke graph path,
- acquisition routes are wired to the bespoke orchestrator,
- graph-generation routes now launch bespoke graph runs,
- source artifacts are preserved in MinIO,
- chunking and embeddings are persisted in PostgreSQL,
- scheduler concurrency classes and task priorities are active,
- graph progress and graph-ready publication are emitted through the bespoke runtime,
- and the bespoke path has been runtime-validated through vector storage plus the current canonical Neo4j projection slices, including semantic similarity and durable community projection.

### Still blocking end-to-end cutover

- some graph-oriented UI surfaces still depend on graph structures that have not yet been fully rewired to the bespoke-owned community layer,
- and shadow-mode parity has not yet been proven for graph quality or the remaining graph-view projection layers.

### Immediate next milestone

Complete the work described in `docs/architecture/graph-projection-migration.md` so the branch owns both front-door acquisition and downstream graph projection with no legacy runtime dependency.
