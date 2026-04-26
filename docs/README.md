# Documentation System

This repository now treats documentation as an architectural control surface, not as an afterthought.

The goal of the docs system is to keep the platform aligned with four non-negotiable traits:

1. Maximum acquisition quality.
2. Maximum source fidelity.
3. Durable and replayable orchestration.
4. High throughput without sacrificing correctness.

## Truth Hierarchy

Use the following precedence order when deciding what is authoritative:

1. `docs/adr/`
   Architectural decisions and irreversible direction.
2. `docs/philosophy/`
   Product and orchestration doctrine.
3. `docs/architecture/`
   System design, invariants, and operating model.
4. `docs/contracts/`
   Runtime contracts, catalogs, and schema expectations.
5. `docs/ops/`
   Runbooks and operational procedures.
6. `.cursor/rules/*.mdc` and `.cursorrules`
   Enforcement summaries for agent behavior.
7. `.cursor/plans/`
   Temporary planning notes only. These are not the source of truth.

If code, plans, and docs disagree, update either the code or the canonical docs. Do not let a third interpretation emerge in chat only.

## Directory Map

- `docs/philosophy/product-philosophy.md`
  What the platform optimizes for and what it refuses to optimize for.
- `docs/philosophy/orchestration-philosophy.md`
  The doctrine behind the bespoke kernel rewrite.
- `docs/architecture/system-overview.md`
  End-to-end view of the platform and the role of each subsystem.
- `docs/architecture/tri-db-invariants.md`
  Hard storage boundaries for PostgreSQL, Neo4j, and MinIO.
- `docs/architecture/front-door-ingestion.md`
  The single allowed acquisition path for new runs, backfills, and replays.
- `docs/architecture/acquisition-policy.md`
  Exhaustive startup discovery and source-hunting policy.
- `docs/architecture/orchestrator-kernel.md`
  Core kernel primitives, durability expectations, and execution model.
- `docs/architecture/workflow-state-model.md`
  Separation of run state, task frames, attempts, and projections.
- `docs/architecture/transition-model.md`
  How workflow transitions, fan-out, joins, and retries are modeled.
- `docs/architecture/performance-model.md`
  Throughput model, concurrency classes, and backpressure rules.
- `docs/architecture/backfill-and-replay.md`
  How existing sites are reprocessed without bypassing ingestion.
- `docs/architecture/migration-governance.md`
  Guardrails for migrating from LangGraph to the bespoke kernel.
- `docs/architecture/graph-projection-migration.md`
  The completion plan for replacing the legacy graph worker with a true bespoke projection path.
- `docs/architecture/graph-quality-recovery.md`
  Current graph-quality diagnosis and recovery plan for turning bulk-extracted facts into useful investment-intelligence graph views.
- `docs/architecture/alpha-graph-views.md`
  Alpha-oriented graph product views, including the advisor/intermediary graph first-build plan.
- `docs/contracts/graph-persistence.md`
  Durable Postgres contract for extracted graph facts and canonical entity resolution.
- `docs/contracts/`
  Canonical worker, task, and event contracts.
- `docs/ops/`
  Runbooks for replay, recovery, and backfill operations.
- `docs/ops/isolated-bespoke-instance.md`
  Step-by-step runbook for launching the bespoke branch against a fully separate local Postgres, Neo4j, MinIO, backend, and frontend instance.
- `docs/ops/bulk-local-graph-extraction.md`
  Same-day runbook for processing the active bespoke corpus with local or cloud OpenAI-compatible inference and projecting topology/community graphs.
- `docs/adr/`
  Decision log for the kernel rewrite.

## Authoring Rules

- Architecture changes require an ADR if they alter storage boundaries, queue semantics, state shape, cutover strategy, or ingestion path.
- Contract changes require docs updates in `docs/contracts/`.
- New orchestration behavior must be documented before or with the implementation, not after.
- No plan note in `.cursor/plans/` may become effectively permanent without being promoted into `docs/`.

## Current State

This branch is no longer at the "kernel skeleton" stage.

What is already real on the bespoke path:

- FastAPI acquisition traffic is wired to the bespoke orchestrator.
- The durable ledger, task attempts, outbox events, and dead-letter handling exist.
- The runtime has been validated through `MARKET_SIZING -> EXTRACT_COMPANIES -> PLAN_COMPANY_SEARCH -> SEARCH_QUERY -> GLOBAL_DEDUP_URL -> SCRAPE_URL -> BOUNCER_EVALUATION -> VECTOR_STORAGE`.
- Source artifacts are preserved in MinIO and chunked text plus embeddings are stored in PostgreSQL.
- The Data Explorer-facing acquisition data is now fed by the bespoke path.
- `/pipelines/{site_id}/generate-graph` now launches a first-class bespoke graph run.
- Canonical entity, document, `MENTIONS`, and `INTERACTS_WITH` projection slices now write into Neo4j from durable PostgreSQL graph facts.
- Document-level `SIMILAR_TO` edges now project from durable PostgreSQL chunk embeddings.
- Durable community rows and memberships now persist in PostgreSQL before `Community` and `BELONGS_TO` projection in Neo4j.
- Graph-stage progress and graph-ready publication are now emitted by the bespoke runtime.
- A bulk local/OpenAI-compatible inference lane has processed the active bespoke corpus into durable PostgreSQL graph facts for the E&P private equity site.
- Neo4j projection is technically available for that bulk run, but the rendered graph is currently not an acceptable analytical output.
- The next graph-product direction is to build thesis-specific alpha graph views, starting with the advisor/intermediary graph documented in `docs/architecture/alpha-graph-views.md`.

Operationally, current bespoke verification is expected to run against the isolated environment documented in `docs/ops/isolated-bespoke-instance.md`, not the older default local stack. At the current stage of branch work, that active bespoke database environment contains one site; if diagnostics surface multiple historical sites, the query is hitting the wrong database.

What is not yet complete:

- final removal of residual legacy graph dependencies and assumptions from graph-facing surfaces,
- graph-quality recovery on the bulk-extracted corpus, including entity-type normalization, alias-aware canonicalization, relationship normalization, thesis-aware ranking/pruning, and UI views that surface private equity firms and supporting evidence,
- full graph-view parity on the bespoke runtime, especially the UI surfaces that need to consume the new community layer without rendering an uncurated hairball,
- shadow-mode validation of graph quality and projection parity on representative sites,
- and cutover closure under the criteria in `docs/architecture/migration-governance.md`.

The migration is complete only when acquisition and graph projection both run end to end on the bespoke runtime with no legacy runtime dependency and the rendered graph is analytically useful. The current graph-quality recovery plan is tracked in `docs/architecture/graph-quality-recovery.md`.
