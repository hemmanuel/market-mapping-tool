# Product Philosophy

## Mission

Build a market intelligence platform that gives investors a durable, sourceable, high-recall map of an industry, not a lightweight demo graph.

## What We Optimize For

### 1. Evidence over elegance

Every important insight must be traceable to acquired source material. Search snippets, memory recall, and synthesized summaries are not durable evidence on their own.

### 2. Recall over convenience

The platform must bias toward finding the long tail of relevant startups, especially early-stage companies that are underrepresented in naive web or model memory recall.

### 3. Fidelity over shortcuts

If the system can either:

- insert a company quickly into Neo4j, or
- acquire primary sources, persist them, chunk them, embed them, and then project them into the graph,

the second path is the correct one.

### 4. Performance as throughput under correctness

Performance does not mean “cheapest” or “fastest to prototype.” It means the system can process large workloads at high speed without sacrificing provenance, durability, or replayability.

### 5. Investor-grade output

The product should surface:

- startup discovery,
- primary evidence,
- graph structure,
- source attribution,
- and reusable analytical context.

It is not enough to generate an aesthetically pleasing graph if the evidence base is weak.

## Anti-Goals

The platform should not optimize for:

- lowest token usage at the expense of coverage,
- bypass scripts that skip source capture,
- graph-only insertion paths,
- document truncation as a substitute for retrieval,
- or hidden orchestration behavior that cannot be replayed or audited.

## Implications

- Backfills and new-site runs must share the same ingestion front door.
- Original files and HTML must be preserved whenever acquired.
- Neo4j is a projection layer for knowledge navigation, not the sole storage layer for truth.
- Documentation is part of the architecture and must evolve with the system.
