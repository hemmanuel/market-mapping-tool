# Graph Persistence Contract

## Purpose

This contract defines the first durable PostgreSQL layer for the bespoke graph projection path.

It covers:

- document-level extracted graph facts,
- canonical entity records,
- the mapping from raw entity facts to canonical entities,
- canonical relationship records,
- canonical community records,
- and canonical community memberships.

It does not yet cover Neo4j projection audit records beyond the orchestration ledger artifacts. Those belong to later slices.

## Table Set

### `graph_entity_facts`

One row per extracted entity fact from a single Postgres document chunk.

Required lineage fields:

- `run_id`
- `site_id`
- `document_id`
- `task_frame_id`
- `task_attempt_id`

Core fact fields:

- `fact_key`
- `entity_name`
- `normalized_name`
- `entity_type`
- `description`
- `evidence_text`
- `source_url`
- `metadata_json`

Idempotency rule:

- uniqueness is enforced by `(run_id, document_id, fact_key)`.

### `graph_relationship_facts`

One row per extracted relationship fact from a single Postgres document chunk.

Required lineage fields:

- `run_id`
- `site_id`
- `document_id`
- `task_frame_id`
- `task_attempt_id`

Core fact fields:

- `fact_key`
- `source_entity_name`
- `source_entity_normalized_name`
- `target_entity_name`
- `target_entity_normalized_name`
- `relationship_type`
- `exact_quote`
- `source_url`
- `metadata_json`

Optional linkage fields:

- `source_entity_fact_id`
- `target_entity_fact_id`

Idempotency rule:

- uniqueness is enforced by `(run_id, document_id, fact_key)`.

### `canonical_entities`

One row per canonical entity produced by a graph-resolution run.

Required lineage fields:

- `run_id`
- `site_id`
- `task_frame_id`
- `task_attempt_id`

Core fields:

- `canonical_key`
- `canonical_name`
- `normalized_name`
- `entity_type`
- `description`
- `aliases_json`
- `resolution_confidence`
- `status`
- `metadata_json`

Idempotency rule:

- uniqueness is enforced by `(run_id, canonical_key)`.

### `canonical_entity_memberships`

Maps one raw entity fact to its canonical entity within a run.

Required lineage fields:

- `run_id`
- `site_id`
- `task_frame_id`
- `task_attempt_id`

Core fields:

- `canonical_entity_id`
- `graph_entity_fact_id`
- `resolution_reason`
- `confidence`
- `metadata_json`

Resolution rule:

- a raw entity fact may resolve to at most one canonical entity per run.
- uniqueness is enforced by `(run_id, graph_entity_fact_id)`.

### `canonical_relationships`

One row per aggregated canonical relationship within a run.

Required lineage fields:

- `run_id`
- `site_id`
- `task_frame_id`
- `task_attempt_id`

Core fields:

- `canonical_relationship_key`
- `source_canonical_entity_id`
- `target_canonical_entity_id`
- `source_canonical_key`
- `target_canonical_key`
- `relationship_type`
- `normalized_relationship_type`
- `evidence_count`
- `weight`
- `quotes_json`
- `source_urls_json`
- `supporting_fact_ids_json`
- `status`
- `metadata_json`

Aggregation rule:

- canonical relationships are directional.
- uniqueness is enforced by `(run_id, canonical_relationship_key)`.
- the current slice groups raw relationship facts by `(source_canonical_key, target_canonical_key, relationship_type)`.

### `canonical_communities`

One row per community detected over canonical graph state within a run.

Required lineage fields:

- `run_id`
- `site_id`
- `task_frame_id`
- `task_attempt_id`

Core fields:

- `community_key`
- `algorithm`
- `algorithm_version`
- `community_name`
- `summary`
- `member_count`
- `relationship_count`
- `status`
- `metadata_json`

Detection rule:

- communities are derived from canonical graph state, not from raw entities directly,
- uniqueness is enforced by `(run_id, community_key)`,
- and `community_key` should be deterministic from the community member set so retries do not create duplicates.

### `canonical_community_memberships`

Maps one canonical entity to its detected community within a run.

Required lineage fields:

- `run_id`
- `site_id`
- `task_frame_id`
- `task_attempt_id`

Core fields:

- `canonical_community_id`
- `canonical_entity_id`
- `membership_rank`
- `metadata_json`

Membership rule:

- a canonical entity may belong to at most one community per run,
- uniqueness is enforced by `(run_id, canonical_entity_id)`,
- and memberships must be reproducible from durable canonical entities plus canonical relationships.

## Invariants

1. `document_id` always points at `documents.id`, which is the current durable chunk record in PostgreSQL.
2. Neo4j must not become the first durable home for extracted graph facts.
3. Every stored graph fact and canonical entity must be attributable to a run, task frame, and task attempt.
4. Canonical resolution must operate on durable `graph_entity_facts`, not transient in-memory clusters only.
5. Neo4j `INTERACTS_WITH` edges must be projected from `canonical_relationships`, not directly from raw relationship facts.
6. Neo4j `Community` nodes and `BELONGS_TO` edges must be projected from durable community tables, not treated as write-only graph annotations.
7. Future projection audit records must build on these tables rather than bypass them.

## Current Resolution Slice

The current implemented canonical resolution slice groups entity facts by `(entity_type, normalized_name)` across a run, then writes canonical entities and memberships durably before projection.

This is a real durable contract, not mock data, but it is not the final alias-resolution strategy. On the active bulk-extracted E&P private equity corpus, this exact-match strategy is known to fragment useful entities across legal-name variants, spelling variants, and model-generated type variants.

The next resolution slice must preserve the durable membership contract while adding:

- normalized graph categories alongside raw extracted types,
- legal suffix and alias cleanup,
- conservative fuzzy or embedding-assisted clustering for high-value entity classes,
- source-backed merge confidence,
- and deterministic replay from `graph_entity_facts`.

## Current Relationship Slice

The current implemented relationship slice aggregates raw relationship facts only when both endpoints already resolve to canonical entities in the same run.

This is a real durable contract, not mock data, but it is not the final relationship synthesis strategy. The current slice groups by exact `(source_canonical_key, target_canonical_key, relationship_type)`, which can split equivalent investment, acquisition, ownership, advisory, and operating relationships across many labels.

The next relationship slice must preserve source quotes and supporting fact IDs while adding a normalized strategic relationship vocabulary, confidence modeling, and broader evidence fusion on top of `canonical_relationships`.

## Current Community Slice

The current implemented community slice writes durable community detection outputs and community memberships derived from canonical graph state.

Those rows are now the source of truth for downstream `Community` node projection, `BELONGS_TO` edges, and community summaries rather than relying on transient Neo4j-only annotations.
