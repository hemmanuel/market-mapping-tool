# Graph Quality Recovery Plan

## Purpose

This document records the current state of the bespoke graph after the first large bulk-local extraction run and defines the recovery plan for making the graph analytically useful.

The current problem is not primarily that the corpus is empty or that Neo4j cannot render a graph. The active bespoke corpus has already been embedded in PostgreSQL, bulk graph extraction has produced durable graph facts, and the projection path can create canonical entities, relationships, documents, mentions, and graph edges in Neo4j.

The current problem is quality: the rendered graph is too noisy, too fragmented, and too weakly aligned to the investment thesis for `Upstream Oil & Gas (E&P) for Private Equity`.

## Current State

The active bespoke environment is the isolated stack documented in `docs/ops/isolated-bespoke-instance.md`.

Current facts:

- The active site is `d9f940ea-982c-4a04-8c6b-2d653457cf9a`.
- The corpus contains roughly `297k` embedded PostgreSQL document chunks from roughly `548` source URLs.
- The expensive bulk extraction pass has already processed the corpus through local or OpenAI-compatible inference.
- Raw extracted graph facts are stored in PostgreSQL, not only in Neo4j.
- Neo4j projection is technically functional, but the current graph view is not acceptable as a market-intelligence output.

The current graph should be treated as a failed quality candidate, not as a failed data-acquisition run.

The investment-facing graph-product direction is tracked in `docs/architecture/alpha-graph-views.md`. That document defines the alpha graph catalog and prioritizes the advisor/intermediary graph as the first purpose-built view.

## Current Failure Mode

The first bulk graph run optimized for throughput and durable extraction. It did not yet preserve enough of the legacy graph worker's quality controls.

Observed or likely causes:

- The bulk extractor uses a generic graph extraction prompt rather than a site-specific ontology prompt.
- The extraction pass processes the broad corpus rather than applying a semantic relevance funnel before graph construction.
- Entity types are unconstrained, so investment-relevant entities may appear under many labels such as `Private Equity Firm`, `Investment Firm`, `Asset Manager`, `Financial Sponsor`, `Fund`, or `Unknown` instead of the frontend-visible `Investor`.
- Canonical entity resolution currently groups by exact `(entity_type, normalized_name)`, which fragments aliases and legal-name variants.
- Relationship aggregation currently groups by exact endpoint pair plus exact relationship type, which fragments semantically identical relationships such as `BACKED`, `INVESTED_IN`, `SPONSORED`, and `FUNDED`.
- Frontend graph queries currently pull limited weighted slices from projected Neo4j state. They are not yet thesis-aware enough to surface private equity, portfolio-company, investment-bank, law-firm, asset, basin, and transaction subgraphs.
- Dense uncurated force-directed views produce a hairball even when useful signal is present in the raw facts.

## Non-Goal

Do not rerun the full 20-hour extraction pass until diagnostics prove that the raw PostgreSQL fact tables genuinely lack the expected private-equity and oil-and-gas signal.

The expensive extraction output is an asset. The immediate recovery plan is to reuse it and rebuild downstream interpretation, canonicalization, projection, and UI ranking.

## Diagnostic Gate

Before changing extraction, inspect durable PostgreSQL graph facts for evidence that the signal exists.

Check:

- entity names containing private-equity indicators such as `capital`, `partners`, `equity`, `holdings`, `management`, `sponsor`, `fund`, and known E&P investor names,
- type distribution for those entities,
- relationship types attached to those entities,
- source URL diversity and evidence counts,
- whether entities are present in raw `graph_entity_facts` but hidden or fragmented after canonicalization,
- and whether high-value relationships are present in `graph_relationship_facts` but lost through type mismatch or endpoint fragmentation.

If the signal exists in raw facts, continue with downstream recovery. If the signal is truly missing, run a targeted second-pass extraction only over high-relevance chunks.

## Recovery Plan

The first implemented recovery slice is deterministic and replayable. It adds graph normalization helpers, normalized entity-type grouping, alias-key canonicalization, normalized relationship aggregation, active/inactive canonical state replacement, and investor-focused graph API/UI views. It does not yet add embedding-based clustering or a targeted second extraction pass.

### 1. Normalize Entity Types

Add a graph-type normalization layer before canonical persistence and Neo4j projection.

Initial mapping examples:

- `Private Equity Firm`, `Financial Sponsor`, `Investment Firm`, `Asset Manager`, `Fund`, `Investment Company` -> `Investor`
- `Operator`, `E&P Company`, `Oil Producer`, `Exploration Company`, `Portfolio Company` -> `Company`
- `Investment Bank`, `Law Firm`, `Advisor`, `Consultant`, `Service Provider` -> `ServiceProvider`
- `Basin`, `Play`, `Field`, `Asset`, `Acreage` -> `Asset`
- `Regulator`, `Agency`, `Commission`, `Government Body` -> `RegulatoryBody`
- `Person`, `Executive`, `Founder`, `Partner` -> `Person`

The normalized type should be preserved alongside the raw type so downstream views can use stable categories without losing provenance.

### 2. Improve Canonical Entity Resolution

Replace exact-match-only resolution with a layered resolver:

1. normalize punctuation, case, whitespace, and legal suffixes,
2. preserve exact normalized-name grouping as the first deterministic pass,
3. add alias cleanup for common legal forms such as `LLC`, `LP`, `Ltd.`, `Inc.`, `Corp.`, `Holdings`, and fund suffixes,
4. add fuzzy matching for near-identical names,
5. add embedding-based clustering for high-value entity types where name variants are common,
6. require conservative confidence thresholds and provenance for merges,
7. keep every raw fact mapped to exactly one canonical entity per run.

This phase should make private equity firms, operators, advisors, and assets appear as durable hub nodes instead of fragmented variants.

### 3. Normalize Relationship Types

Add a strategic relationship vocabulary for the graph views.

Initial mapping examples:

- `BACKED`, `INVESTED_IN`, `SPONSORED`, `FUNDED`, `PROVIDED_CAPITAL_TO` -> `INVESTED_IN`
- `ACQUIRED`, `BOUGHT`, `PURCHASED`, `MERGED_WITH` -> `ACQUIRED`
- `OWNS`, `HOLDS`, `CONTROLS`, `PORTFOLIO_COMPANY_OF` -> `OWNS_OR_CONTROLS`
- `ADVISED`, `REPRESENTED`, `COUNSEL_TO`, `UNDERWROTE`, `PLACED` -> `ADVISED`
- `OPERATES_IN`, `HAS_ASSET_IN`, `DRILLS_IN`, `PRODUCES_FROM` -> `OPERATES_IN`
- `PARTNERED_WITH`, `JOINT_VENTURE_WITH`, `COLLABORATED_WITH` -> `PARTNERED_WITH`

Relationship normalization should increase edge weights by combining equivalent evidence instead of scattering it across many relationship labels.

### 4. Add Thesis-Aware Ranking And Pruning

Do not render every extracted fact by default.

Rank canonical entities and relationships using:

- normalized entity type,
- evidence count,
- unique source URL count,
- relationship diversity,
- source-document quality,
- connection to E&P/oil-and-gas terms,
- connection to investor, portfolio-company, advisor, asset, basin, acquisition, and financing concepts,
- and whether the node participates in high-value relationship types.

Prune or demote:

- singleton low-evidence nodes,
- generic concepts,
- boilerplate page entities,
- low-evidence `Unknown` nodes,
- document labels and navigation text,
- and overly broad locations or generic industries unless they connect to investment-relevant entities.

### 5. Fix Graph API And UI Views

The default graph view should be curated and thesis-aware, not a raw force-directed dump.

Add or repair views for:

- investors,
- investor-to-portfolio-company relationships,
- investor-to-asset or basin relationships,
- advisor and intermediary relationships,
- company-to-advisor relationships,
- M&A and financing relationships,
- orphan or under-mapped assets,
- distress and forced-seller signals,
- management team and serial entrepreneur networks,
- basin specialization,
- relationship rarity,
- temporal momentum,
- communities,
- and source-document evidence.

The frontend should be able to answer "which PE firms matter here, why, and what evidence supports that" before it attempts to show the entire topology.

The first new alpha view should be the advisor/intermediary graph. It should surface `ServiceProvider` nodes such as investment banks, law firms, consultants, reserve engineers, placement agents, brokers, and transaction advisors, then rank their connections to investors, operators, assets, people, and source documents by specificity, evidence count, source diversity, and thesis relevance.

### 6. Rebuild From Durable Facts

After type normalization, canonicalization, relationship normalization, ranking, and UI query changes are in place:

1. keep raw `graph_entity_facts` and `graph_relationship_facts`,
2. rebuild canonical entities and memberships,
3. rebuild canonical relationships,
4. clear and reproject Neo4j graph state for the active run,
5. render thesis-aware graph slices first,
6. then evaluate whether community detection is useful on the cleaned graph.

This rebuild should use the expensive facts already in PostgreSQL and should not require the full extraction pass.

## Target Acceptance Criteria

The graph is acceptable only when:

- known private equity shops from the corpus appear as visible, consolidated nodes,
- investor nodes connect to portfolio companies, transactions, assets, basins, advisors, or source documents with evidence,
- entity aliases do not split obvious firms into many weak nodes,
- equivalent relationship labels aggregate into meaningful edge weights,
- the default UI view is readable without turning into a hairball,
- every visible relationship can be traced back to source quotes or source URLs,
- and the cleaned graph can be replayed from PostgreSQL facts without direct-to-Neo4j extraction shortcuts.

## When To Re-Extract

Only run a second extraction pass if the diagnostic gate shows that important private-equity or oil-and-gas entities are absent from raw PostgreSQL graph facts.

If needed, the second pass should be targeted:

- select high-relevance chunks using embeddings, source URLs, and keyword filters,
- inject the site ontology into the extraction prompt,
- explicitly ask for private equity firms, investment banks, law firms, operators, portfolio companies, management teams, assets, basins, transactions, and financing events,
- and persist results back into the same durable graph fact tables.

Do not treat a targeted second pass as a replacement for downstream graph-quality recovery.
