# Worker Catalog

The bespoke kernel is no longer a worker wish list only. This document now distinguishes between the workers already implemented on the branch, the workers present but not on the active path, and the remaining migration gaps that are no longer about missing worker coverage.

## Implemented on this branch

- `MarketSizingWorker`
- `CompanyExtractionWorker`
- `PlannerWorker`
- `SearchQueryWorker`
- `GlobalDedupWorker`
- `ScraperWorker`
- `BouncerWorker`
- `VectorStorageWorker`
- `GraphDocumentSelectionWorker`
- `GraphFactExtractionWorker`
- `GraphExtractionBarrierWorker`
- `CanonicalEntityResolutionWorker`
- `PersistCanonicalEntitiesWorker`
- `CanonicalRelationshipAggregationWorker`
- `PersistCanonicalRelationshipsWorker`
- `ProjectCanonicalEntitiesWorker`
- `ProjectDocumentMentionsWorker`
- `ProjectInteractsWithWorker`
- `ProjectSemanticSimilarityWorker`
- `ProjectCommunitiesWorker`
- `ProjectCommunitySummariesWorker`
- `PruneGraphWorker`
- `PublishGraphReadyWorker`

These workers currently cover the bespoke acquisition path through source preservation, chunking, embedding persistence, raw graph-fact extraction, canonical entity persistence, canonical relationship persistence, semantic document similarity projection, durable community persistence and summary overlays, idempotent Neo4j graph pruning, and graph-ready publication.

## Present but not on the active acquisition transition path

- `EnrichmentWorker`

This worker exists in the codebase but is not yet the canonical centerpiece of the bespoke runtime.

## Remaining gaps for end-to-end migration

- optional future split of graph-fact persistence into its own worker instead of keeping it inside `GraphFactExtractionWorker`,
- richer relationship normalization and confidence modeling beyond the current deterministic aggregation slice,
- and graph-view/UI parity work that depends on the newly projected community layer.

## Design Rules

- one worker should own one clear responsibility,
- durable side effects should be explicit,
- worker outputs should be typed and attributable,
- and graph projection workers must persist their intermediate facts in PostgreSQL before projecting into Neo4j.
