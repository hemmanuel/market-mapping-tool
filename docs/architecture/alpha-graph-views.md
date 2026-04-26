# Alpha Graph Views

## Purpose

The graph should not be judged by whether it can render every extracted node at once. The most valuable graph product is a set of thesis-specific views that surface non-obvious investment signal with evidence.

For `Upstream Oil & Gas (E&P) for Private Equity`, "alpha" means finding private-market relationships, hidden asset ownership, deal intermediaries, sponsor patterns, distressed sellers, and emerging basin concentration before they are obvious in generic company lists.

These graph views must preserve the platform invariants:

- PostgreSQL remains the durable source of extracted facts, canonical entities, relationships, communities, and evidence.
- Neo4j remains a replayable projection optimized for traversal and rendering.
- MinIO and source URLs remain the evidence trail behind visible relationships.
- The UI should render curated analytical slices, not an unfiltered hairball.

## Alpha Graph Catalog

### 1. Sponsor To Asset Graph

Question: which private equity firms, sponsors, and funds are connected to operators, assets, acreage, fields, basins, and plays?

Primary nodes:

- `Investor`
- `Company`
- `Asset`
- `Person`
- `Document`

Primary relationships:

- `INVESTED_IN`
- `OWNS_OR_CONTROLS`
- `ACQUIRED`
- `OPERATES_IN`
- `PARTNERED_WITH`
- `MENTIONS`

Alpha signal:

- sponsor concentration in a basin, play, or operator type,
- private operators linked to sophisticated sponsors,
- asset mentions across obscure source documents before broad market coverage,
- and repeated sponsor behavior across multiple platform companies.

### 2. Advisor And Intermediary Graph

Question: which investment banks, law firms, consultants, engineers, and other service providers sit closest to deal flow?

Primary nodes:

- `ServiceProvider`
- `Investor`
- `Company`
- `Asset`
- `Person`
- `Document`

Primary relationships:

- `ADVISED`
- `REPRESENTED`
- `FINANCED`
- `VALUED`
- `MARKETED`
- `PARTNERED_WITH`
- `MENTIONS`

Alpha signal:

- boutique banks repeatedly tied to specific basins, sponsors, or operators,
- law firms appearing across transactions before the buyer or seller is obvious,
- technical advisors or reserve engineers recurring near asset sales,
- and service providers that bridge otherwise separate PE ecosystems.

This is the first alpha graph to build because intermediaries are often closer to private-market activity than public company lists.

### 3. Orphan And Under-Mapped Asset Graph

Question: which assets have strong evidence but weak ownership, sponsor, or operator clarity?

Primary nodes:

- `Asset`
- `Company`
- `Investor`
- `RegulatoryBody`
- `Document`

Primary relationships:

- `OPERATES_IN`
- `OWNS_OR_CONTROLS`
- `PERMITTED_BY`
- `MENTIONS`
- `ASSOCIATED_WITH`

Alpha signal:

- assets with many source mentions but unclear ownership,
- operationally meaningful fields or acreage with weak sponsor visibility,
- regulatory filings that mention assets before market-facing sources do,
- and technical asset clusters not yet attached to an obvious buyer universe.

### 4. Distress And Forced-Seller Graph

Question: which operators or assets may need capital, refinancing, divestiture, restructuring, or a partner?

Primary nodes:

- `Company`
- `Asset`
- `Investor`
- `Lender`
- `RegulatoryBody`
- `Person`
- `Document`

Primary relationships:

- `OWES`
- `DEFAULTED`
- `RESTRUCTURED`
- `LITIGATED`
- `PERMITTED_BY`
- `SOLD_TO`
- `MENTIONS`

Alpha signal:

- operators linked to debt, covenant pressure, bankruptcy, litigation, plugging liability, or permit issues,
- assets connected to regulatory friction but still operationally valuable,
- aging sponsor-backed platforms that may need exits,
- and fragmented portfolios that could become acquisition candidates.

### 5. Management Team And Serial Entrepreneur Graph

Question: which executives, founders, operating partners, and technical teams repeatedly create, sell, and restart E&P platforms?

Primary nodes:

- `Person`
- `Company`
- `Investor`
- `Asset`
- `Document`

Primary relationships:

- `FOUNDED`
- `LED`
- `BACKED_BY`
- `SOLD_TO`
- `ACQUIRED`
- `OPERATES_IN`
- `MENTIONS`

Alpha signal:

- executives repeatedly backed by the same sponsors,
- teams forming new entities after exits,
- operators who bridge multiple investors or basins,
- and people networks that reveal likely future platforms before company datasets do.

### 6. Basin Specialization Graph

Question: which investors, operators, and service providers are unusually concentrated in specific basins, formations, or plays?

Primary nodes:

- `Investor`
- `Company`
- `Asset`
- `ServiceProvider`
- `Document`

Primary relationships:

- `OPERATES_IN`
- `INVESTED_IN`
- `ACQUIRED`
- `SERVICES`
- `PARTNERED_WITH`
- `MENTIONS`

Alpha signal:

- PE firms repeatedly active in obscure basins,
- service providers tied to emerging operational themes,
- operators that are peripheral in broad categories but central in a micro-play,
- and local specialization that does not show up in generic industry taxonomies.

### 7. Relationship-Rarity Graph

Question: which relationships are rare, specific, well-supported, and therefore more likely to be useful than generic co-mentions?

Primary nodes:

- any canonical entity type, filtered by relationship quality.

Primary relationships:

- high-specificity relationships such as `ADVISED`, `FINANCED`, `ACQUIRED`, `INVESTED_IN`, `OWNS_OR_CONTROLS`, `PARTNERED_WITH`, and `OPERATES_IN`.

Alpha signal:

- rare relationships backed by multiple independent sources,
- low-frequency but high-specificity edges,
- and connections that would be hidden if the graph only ranked by raw degree.

Recommended edge score:

```text
alpha_edge_score =
  evidence_count
  * source_diversity_weight
  * relationship_specificity_weight
  * rarity_weight
  * thesis_relevance_weight
```

### 8. Temporal Momentum Graph

Question: which entities, assets, sponsors, and relationships are newly accelerating?

Primary nodes:

- same canonical entities as the sponsor, intermediary, asset, and distress views.

Primary relationships:

- any high-value relationship with first-seen, last-seen, source-date, and mention-velocity metadata.

Alpha signal:

- new sponsor/operator/asset relationships,
- rising mentions of a basin, asset, or intermediary,
- recently formed companies or platforms,
- and entities entering a network that historically did not include them.

## Priority Order

Build alpha views in this order:

1. Advisor and Intermediary Graph.
2. Sponsor To Asset Graph.
3. Orphan And Under-Mapped Asset Graph.
4. Relationship-Rarity Graph.
5. Distress And Forced-Seller Graph.
6. Management Team And Serial Entrepreneur Graph.
7. Basin Specialization Graph.
8. Temporal Momentum Graph.

The intermediary graph comes first because it can expose deal-flow infrastructure even when buyers, sellers, or assets are fragmented. It also gives a high-signal validation target for whether `ServiceProvider` normalization is working.

## First Build: Advisor And Intermediary Graph

### Objective

Create a graph view that surfaces investment banks, law firms, consultants, reserve engineers, technical advisors, and other service providers connected to investors, companies, assets, people, and source documents.

The view should answer:

- Which intermediaries appear closest to private equity E&P deal activity?
- Which investors and operators are repeatedly connected to those intermediaries?
- Which assets, basins, or transactions explain the connection?
- What source URLs or quotes support each edge?

### Required Entity Coverage

The first version should rely on normalized canonical entity types already produced by graph recovery:

- `ServiceProvider`
- `Investor`
- `Company`
- `Asset`
- `Person`
- `RegulatoryBody`
- `Document`

The most important quality requirement is improving `ServiceProvider` resolution so raw labels such as `Investment Bank`, `Law Firm`, `Advisor`, `Consultant`, `Engineering Firm`, `Reserve Engineer`, `Broker`, and `Placement Agent` become visible in one stable graph category.

### Required Relationship Coverage

The first version should rank these relationship families highest:

- `ADVISED`
- `REPRESENTED`
- `FINANCED`
- `VALUED`
- `MARKETED`
- `PARTNERED_WITH`
- `INVESTED_IN`
- `ACQUIRED`
- `OWNS_OR_CONTROLS`
- `OPERATES_IN`

If raw extraction does not yet produce `REPRESENTED`, `FINANCED`, `VALUED`, or `MARKETED` consistently, the graph should still include those labels in the normalized relationship vocabulary so targeted second-pass extraction can populate them later.

### Scoring

The first ranking model should favor relationships that are specific, source-backed, and near deal flow.

Recommended node score:

```text
intermediary_node_score =
  25 * count(ADVISED or REPRESENTED or FINANCED or MARKETED edges)
  + 15 * count(unique Investor neighbors)
  + 12 * count(unique Company neighbors)
  + 10 * count(unique Asset neighbors)
  + 8  * count(unique source_urls)
  + 5  * count(unique Person neighbors)
  - 10 * generic_name_penalty
```

Recommended edge score:

```text
intermediary_edge_score =
  relationship_weight
  + evidence_count
  + 4 * unique_source_url_count
  + 10 if relationship_type in [ADVISED, REPRESENTED, FINANCED, MARKETED, VALUED]
  + 6  if one endpoint is Investor
  + 6  if one endpoint is Asset or Company
```

Generic service providers, boilerplate organizations, locations, and weak one-off co-mentions should be demoted unless they connect to high-value relationship types.

### Data Checks Before Implementation

Before writing frontend UI work, run durable fact diagnostics in PostgreSQL:

- count canonical `ServiceProvider` entities for the active run,
- list top `ServiceProvider` names by evidence count and relationship count,
- inspect relationship-type distribution around `ServiceProvider` nodes,
- sample source URLs and quotes for the top 25 intermediary edges,
- verify that expected raw labels such as investment banks and law firms are being normalized into `ServiceProvider`,
- and identify missing relationship labels that may require targeted second-pass extraction.

### API Shape

Add a dedicated graph theme or endpoint for intermediaries.

Minimum response fields:

- source node id, name, type, score, community metadata,
- target node id, name, type, score, community metadata,
- normalized relationship type,
- edge weight and alpha score,
- quotes,
- source URLs,
- evidence count,
- unique source count.

The initial Cypher slice should start from `ServiceProvider` nodes, expand to high-value neighbors, score the relationships, and limit by score rather than by raw graph degree.

### UI Shape

The UI should present this as a curated graph view, not as a raw all-entities view.

Initial UI behavior:

- add an `Intermediaries` theme button,
- use a distinct color for `ServiceProvider`,
- size intermediary nodes by intermediary score,
- emphasize `ADVISED`, `REPRESENTED`, `FINANCED`, `VALUED`, and `MARKETED` edges,
- expose source URLs and quotes in the edge detail panel,
- and allow filtering to investment banks, law firms, consultants, and technical advisors once subtype metadata is available.

### Implementation Plan

1. Diagnostics:
   Query PostgreSQL and Neo4j to confirm current `ServiceProvider` volume, relationship labels, source coverage, and top candidate intermediary nodes.

2. Normalization improvements:
   Extend entity-type and relationship-type normalization for investment banks, law firms, reserve engineers, placement agents, brokers, legal counsel, transaction advisors, and technical consultants.

3. Scoring:
   Add an intermediary scoring query in the graph API using relationship specificity, evidence count, unique source URL count, endpoint type, and service-provider centrality.

4. API:
   Add an `intermediaries` graph theme that returns only high-scoring intermediary-centered neighborhoods.

5. UI:
   Add the `Intermediaries` graph theme, service-provider legend treatment, and edge evidence display.

6. Validation:
   Manually inspect the top 50 intermediary nodes and top 100 intermediary edges for source-backed usefulness.

7. Recovery loop:
   If investment banks and law firms are present in raw facts but hidden after canonicalization, fix normalization and rebuild from PostgreSQL facts. If they are absent from raw facts, run a targeted second-pass extraction over high-relevance chunks only.

### Acceptance Criteria

The first intermediary graph is acceptable when:

- recognizable investment banks, law firms, advisors, consultants, or reserve engineers appear as `ServiceProvider` nodes,
- those nodes connect to investors, operators, assets, transactions, people, or source documents,
- top edges show specific relationship labels rather than only generic co-mentions,
- every top relationship has at least one source URL or quote,
- the rendered graph is readable at default limits,
- and the view surfaces at least a few non-obvious intermediaries worth investigating.

## Relationship To Graph Quality Recovery

This document extends `docs/architecture/graph-quality-recovery.md`. The recovery plan repairs the general graph substrate. The alpha graph views define the investment-facing products that should sit on top of that substrate.

Do not add new direct-to-Neo4j extraction shortcuts for these views. If the graph needs better signal, improve normalization, scoring, targeted extraction, or replay from durable PostgreSQL facts.
