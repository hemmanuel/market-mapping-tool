# Acquisition Policy

## Objective

Acquire the maximum useful evidence for a market while preserving quality, provenance, and replayability.

## Startup Discovery Policy

The system must not rely on model memory alone for startup discovery. It must combine:

- model recall,
- public web search,
- aggregator hunting,
- funding and investor source search,
- and direct company source hunting.

This is especially important for pre-seed and seed companies, which are underrepresented in generic recall-heavy approaches.

## Source-Hunting Policy

For each relevant company, the system should attempt to acquire high-value evidence in roughly this order:

1. official website and product pages,
2. about/team/founder pages,
3. funding pages and investor pages,
4. press releases and funding announcements,
5. pitch decks and technical PDFs,
6. directory/profile pages when they add unique evidence.

## Primary Artifact Preference

When a company or topic has a PDF, PPTX, HTML page, or other durable source, prefer acquiring and preserving it over only extracting snippets from search results.

## Evidence Exhaustion

A topic is exhausted only when:

- the search space has been explored across the major query families,
- primary-source attempts have been made,
- and remaining gaps are explicitly known rather than silently ignored.

## Rejection Criteria

Reject or down-rank sources that are:

- thin boilerplate pages,
- obvious paywall fragments without useful text,
- duplicate mirrors,
- or generic aggregator pages that add no new evidence.

## Output Requirements

A successful acquisition should leave behind:

- preserved source artifact or text,
- durable provenance metadata,
- chunked text in Postgres,
- embeddings in Postgres,
- and graph projections in Neo4j when applicable.
