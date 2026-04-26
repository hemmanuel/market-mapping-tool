# Bespoke Graph Projection Migration

## Purpose

This document defines the remaining work required to finish the migration from legacy graph generation to a true bespoke graph projection path.

It is the architecture-of-record for closing the current gap between:

- bespoke front-door acquisition, which is already live on this branch through durable graph persistence and projection inputs,
- and the still-incomplete graph surface, where the last legacy UI assumptions, parity checks, and cutover tasks have not yet been fully replaced.

This document now focuses specifically on graph migration work.

The enrichment cutover is tracked separately in `docs/architecture/company-enrichment-cutover.md`, but both paths are expected to consume the same durable front-door evidence base.

The current graph-quality recovery plan is tracked in `docs/architecture/graph-quality-recovery.md`. That document is now the source of truth for the immediate remediation of the bulk-extracted E&P private equity graph.

## Current Branch Reality

The bespoke runtime already owns:

- market sizing,
- company extraction,
- search planning,
- URL search,
- global URL deduplication,
- scraping and raw artifact preservation,
- relevance gating,
- chunking and embedding persistence,
- and durable orchestration state in PostgreSQL.

That same front-door corpus is now also used by company enrichment:

- `EXTRACT_COMPANIES` emits enrichment work on the active DAG,
- enrichment waits for company-scoped source acquisition to settle,
- and dossier synthesis now reads persisted PostgreSQL documents rather than side-channel fetched text.

The bespoke runtime does not yet own:

- richer canonical relationship normalization beyond the current deterministic aggregation slice,
- or the final graph-view parity layers that still depend on legacy-era projected data.

`/pipelines/{site_id}/generate-graph` now launches a first-class bespoke `graph` objective, seeded from already persisted PostgreSQL documents rather than a legacy background stub.

The first graph-runtime slice is now present on the bespoke path:

- `VECTOR_STORAGE` can emit graph document selection work,
- `GraphDocumentSelectionWorker` can materialize newly written Postgres chunks into graph extraction tasks,
- and `GraphFactExtractionWorker` can extract and durably persist raw graph facts into PostgreSQL with run, task, and attempt lineage.

The second graph-runtime slice is now also present:

- `GraphExtractionBarrierWorker` provides the first durable fan-in step after raw extraction,
- `CanonicalEntityResolutionWorker` and `PersistCanonicalEntitiesWorker` build durable canonical entity state in PostgreSQL,
- `ProjectCanonicalEntitiesWorker` projects canonical entities into Neo4j,
- and `ProjectDocumentMentionsWorker` projects `Document` nodes plus `MENTIONS` edges from durable Postgres state.

The third graph-runtime slice is now present as well:

- `CanonicalRelationshipAggregationWorker` builds durable canonical relationship state from raw relationship facts plus canonical memberships,
- `PersistCanonicalRelationshipsWorker` stores those aggregated relationships in PostgreSQL,
- and `ProjectInteractsWithWorker` projects bespoke `INTERACTS_WITH` edges into Neo4j with `weight`, `quotes`, and `source_urls` properties aligned to the current graph views.

The next API/runtime slice is now also present:

- `/pipelines/{site_id}/generate-graph` starts a bespoke graph run instead of only toggling a placeholder status,
- the graph objective seeds `GRAPH_DOCUMENT_SELECTION` from the existing durable document corpus,
- and graph stage/status updates are emitted as ledger-backed `graph_progress` events.

The next projection-integrity slice is now present as well:

- `PruneGraphWorker` removes stale bespoke-owned `CanonicalEntity`, `Document`, and `MENTIONS` state before publication,
- `PublishGraphReadyWorker` verifies Neo4j counts against durable PostgreSQL facts and marks the site graph `ready`,
- and the bespoke export path now reads from canonical `INTERACTS_WITH` edges instead of legacy raw-relationship structures.

The next document-graph slice is now present too:

- `ProjectSemanticSimilarityWorker` derives `SIMILAR_TO` edges from durable PostgreSQL chunk embeddings,
- those similarity edges are projected idempotently into Neo4j with stable keys,
- and graph-ready publication now verifies the semantic edge count from durable task output before the site is marked ready.

The next community slice is now present as well:

- `ProjectCommunitiesWorker` persists durable `canonical_communities` and `canonical_community_memberships` rows before projecting `Community` nodes and `BELONGS_TO` edges,
- `ProjectCommunitySummariesWorker` updates those durable rows with descriptive names and summaries before syncing them back into Neo4j,
- and graph-ready publication now verifies community and community-membership counts alongside the rest of the bespoke projection.

This is still not full graph cutover because richer entity-type normalization, alias-aware canonicalization, relationship normalization, thesis-aware ranking, broader graph-view parity, and final shadow-mode verification remain incomplete.

The first large bulk-local extraction run proved the throughput path and produced durable PostgreSQL graph facts for the active E&P private equity site. It also exposed a quality regression: the projected Neo4j graph can render, but the default UI graph is too noisy, too fragmented, and insufficiently focused on private equity firms, portfolio companies, advisors, assets, basins, and source-backed transactions. Treat this as a downstream graph-quality failure, not as evidence that the front-door corpus or raw extraction tables should be discarded.

It is also no longer accurate to treat graph migration as the only bespoke consumer of the front door. Graph and enrichment now share the same acquisition lineage, document corpus, and Postgres-first ownership model, even though their remaining rollout steps differ.

## Relationship To Enrichment Cutover

Graph migration and enrichment cutover are now sibling tracks on top of the same bespoke runtime:

- the front door acquires and stores evidence once,
- graph projection consumes that corpus to build canonical graph state,
- and enrichment consumes that corpus to synthesize company dossiers and, when migrations are applied, normalized enrichment tables.

The architectural split is now:

- this document tracks the remaining graph-specific cutover, parity, and verification work,
- `docs/architecture/company-enrichment-cutover.md` tracks enrichment-specific persistence, projection, and rollout timing,
- and `docs/architecture/front-door-ingestion.md` remains the rule-of-record that both paths must obey.

## Target End State

The completed system must satisfy all of the following:

- a site run can execute acquisition and graph projection without a legacy runtime dependency,
- Neo4j becomes a projection target rather than a hidden work queue or extraction scratchpad,
- graph extraction, canonicalization, aggregation, and projection each have durable task boundaries,
- every graph mutation is attributable to a run, task, and attempt lineage,
- graph progress is emitted through durable outbox events,
- existing graph views are backed by data produced by the bespoke runtime,
- graph views surface thesis-relevant entities and evidence instead of uncurated raw topology,
- and graph replay remains compatible with the same durable evidence base used by enrichment replay.

## Non-Negotiable Rules

- No mock graph data.
- No temporary direct-to-Neo4j shortcuts.
- No graph-only ingestion path that bypasses PostgreSQL durability.
- No final cutover until graph outputs can be replayed from durable facts and are accepted as analytically useful.
- No bespoke graph phase that silently falls back to the legacy graph worker.
- No graph assumptions that require enrichment to maintain a second acquisition or persistence system.
- No full-corpus graph re-extraction until diagnostics show the raw PostgreSQL graph fact tables lack the required signal.

## Required Runtime Shape

### New workflow objective

Add an explicit graph projection objective to the bespoke runtime. This may be a dedicated run type or a follow-on run chained from acquisition completion, but it must be first-class in the ledger and transition model.

### Durable graph fact layer

Persist extracted graph facts in PostgreSQL before Neo4j projection. The durable layer must be rich enough to support:

- extracted entities,
- extracted claims and evidence,
- canonical entity mappings,
- canonical relationships,
- document-to-entity mentions,
- semantic similarity candidates,
- community inputs and outputs,
- and graph projection audit records.

### Stage barriers and fan-in

The transition model must support graph-specific barriers after vector storage so the kernel can:

- wait until the relevant document set is stable,
- fan out document-level extraction,
- fan in for canonical resolution,
- fan back out for projection,
- and publish graph readiness only after projection integrity checks succeed.

## Required Workers

The target runtime now centers on the following worker responsibilities. These workers are now implemented on this branch; the remaining work is cutover, parity validation, and refinement rather than missing worker coverage:

- `GraphDocumentSelectionWorker`
  Select the document set eligible for graph extraction.
- `GraphFactExtractionWorker`
  Extract entity, relationship, and evidence candidates from document content and durably persist raw graph facts.
- `CanonicalEntityResolutionWorker`
  Resolve entity identity across noisy extraction outputs.
- `PersistCanonicalEntitiesWorker`
  Store canonical mappings and provenance.
- `CanonicalRelationshipAggregationWorker`
  Merge and score relationship evidence across documents.
- `ProjectCanonicalEntitiesWorker`
  Project canonical entities into Neo4j.
- `ProjectDocumentMentionsWorker`
  Project document nodes plus document-to-entity mention edges.
- `ProjectInteractsWithWorker`
  Project evidence-backed canonical relationships.
- `ProjectSemanticSimilarityWorker`
  Project document-to-document semantic similarity edges from durable embeddings.
- `PruneGraphWorker`
  Remove stale bespoke-owned graph state before publication.
- `PublishGraphReadyWorker`
  Mark graph completion only after projection checks pass.
- `ProjectCommunitiesWorker`
  Build community assignments from canonical graph state.
- `ProjectCommunitySummariesWorker`
  Persist community summaries and descriptive overlays.

## Delivery Phases

### Phase 1: Graph contracts and persistence

Define the relational contracts for graph facts, canonical entities, canonical relationships, and projection audit records. Add the corresponding ledger-compatible or application-compatible tables and migrations.

The first implemented slice now exists in `docs/contracts/graph-persistence.md` and covers:

- `graph_entity_facts`,
- `graph_relationship_facts`,
- `canonical_entities`,
- `canonical_entity_memberships`,
- `canonical_relationships`,
- `canonical_communities`,
- and `canonical_community_memberships`.

### Phase 2: Kernel capability expansion

Extend the transition system and engine where needed for:

- graph objectives,
- stage barriers,
- document-set completion checks,
- and fan-in after document-level extraction.

### Phase 3: Fact extraction

Implement document-level graph extraction using the bespoke LLM client and store its outputs durably in PostgreSQL with explicit provenance.

### Phase 4: Canonical resolution

Implement canonical entity resolution and relationship aggregation as durable tasks, not as hidden in-memory graph logic.

The current exact-match resolution slice is durable but insufficient for the bulk-extracted corpus. The next graph-quality slice must add entity-type normalization, alias cleanup, fuzzy or embedding-assisted clustering for high-value entities, and conservative provenance-preserving merge rules.

### Phase 5: Neo4j projection

Project canonicalized graph state into Neo4j with idempotent writers and durable projection audit records.

### Phase 6: API and UI wiring

Rewire graph-generation routes and graph-progress surfaces to start and observe bespoke runs instead of legacy background behavior.

The current UI wiring can display a projected graph, but the default query shape is not yet a quality gate. The next UI slice must add thesis-aware graph views and ranking for investors, portfolio companies, advisors, assets, basins, M&A, financing, communities, and source evidence.

### Phase 7: Verification and cutover

Run parity checks against the legacy graph output for representative sites, then remove the legacy dependency only after graph quality, durability, and UI parity are accepted.

The active E&P private equity run is now a required verification case. It should pass the acceptance criteria in `docs/architecture/graph-quality-recovery.md` before this migration is considered complete.

## Definition of Done

The migration is complete only when all of the following are true:

- acquisition and graph projection both execute on the bespoke runtime,
- `src/agents/graph_worker.py` is no longer required for the branch's graph path,
- `/pipelines/{site_id}/generate-graph` launches bespoke graph work,
- Neo4j graph data is reproducible from durable PostgreSQL records,
- graph-ready status and graph-progress events are driven by bespoke outbox events,
- the graph UI surfaces operate on bespoke-produced graph state with no legacy runtime dependency,
- the default rendered graph is useful for market intelligence and does not rely on an uncurated hairball view,
- investor, portfolio-company, advisor, asset, basin, transaction, and evidence views are available for the E&P private equity site,
- and graph architecture remains aligned with the same Postgres-first ownership model now used by enrichment.
