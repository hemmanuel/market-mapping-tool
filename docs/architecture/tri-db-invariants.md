# Tri-DB Invariants

The platform intentionally separates concerns across three storage systems. This separation is mandatory.

## PostgreSQL

PostgreSQL is responsible for:

- tenant and site records,
- data source records,
- raw document text,
- chunk records,
- chunk embeddings,
- future orchestration ledger state,
- and durable workflow metadata.

PostgreSQL is the authoritative home for chunk-level semantic state.

### PostgreSQL must not be treated as

- a disposable cache of text,
- a place to store only summaries while originals live nowhere else,
- or a substitute for graph projections.

## Neo4j

Neo4j is responsible for:

- projected entities,
- projected documents,
- navigable relationships,
- graph exploration surfaces,
- and user-facing knowledge structure.

Neo4j is a projection layer. It is not the sole copy of the source truth.

### Neo4j must not be treated as

- the only durable home for discovered companies,
- a place to store business knowledge that skipped source capture,
- or a substitute for chunk-level retrieval state.

## MinIO

MinIO is responsible for:

- original binaries,
- acquired HTML snapshots when applicable,
- and source artifacts required for verifiable attribution.

### MinIO must not be treated as optional

If the system acquires a primary binary or HTML page that underpins downstream reasoning, the artifact must be preserved unless explicitly rejected by policy.

## Cross-Store Invariants

1. A preserved source should be traceable from UI to MinIO or Postgres text.
2. Document-level semantics should roll up from chunk-level evidence in Postgres.
3. Graph nodes and edges in Neo4j should remain explainable by durable source evidence.
4. Replays must not create irreversible divergence between Postgres, MinIO, and Neo4j.
5. Any workflow that writes to Neo4j while skipping source preservation violates the architecture.
