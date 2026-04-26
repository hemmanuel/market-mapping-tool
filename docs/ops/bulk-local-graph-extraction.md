# Bulk Local Graph Extraction

## Purpose

This runbook describes the same-day brute-force graph workflow for the active bespoke corpus.

It exists because the normal orchestrator graph path leases `GRAPH_FACT_EXTRACTION` as remote LLM tasks. That path is durable, but it is not appropriate for processing hundreds of thousands of chunks quickly.

The bulk path keeps the same durable Postgres graph tables, but replaces the slow extraction fan-out with a high-throughput local or cloud OpenAI-compatible inference lane.

## Current Status

The active E&P private equity corpus has completed a large bulk extraction pass. That pass produced durable graph facts in PostgreSQL and proved the high-throughput inference lane.

The current projected graph is not yet acceptable. It renders as a noisy, fragmented graph and does not reliably surface private equity firms, portfolio companies, advisors, assets, basins, and source-backed transactions. Treat this as a downstream graph-quality recovery problem, not as a reason to discard the extracted facts or rerun the full corpus.

Before rerunning extraction, follow `docs/architecture/graph-quality-recovery.md`.

## Active Corpus

Use the isolated bespoke environment from `docs/ops/isolated-bespoke-instance.md`.

The current target site is:

- `d9f940ea-982c-4a04-8c6b-2d653457cf9a`
- `Upstream Oil & Gas (E&P) for Private Equity`

The current corpus is expected to be large:

- roughly `297k` embedded `documents` rows,
- roughly `548` source URLs,
- and one site in `market_bespoke_db`.

If diagnostics show three sites, you are connected to the older default database, not the active bespoke environment.

## Workflow

```mermaid
flowchart TD
    postgresCorpus[PostgresChunks] --> bulkExtractor[BulkLocalExtractor]
    vllmServer[vLLMServer] --> bulkExtractor
    bulkExtractor --> graphFacts[GraphFactsPostgres]
    graphFacts --> finalize[FinalizeBulkRun]
    finalize --> canonicalState[CanonicalGraphState]
    canonicalState --> neo4jProjection[Neo4jProjection]
    neo4jProjection --> communityExplorer[TopologyCommunityExplorer]
```

## Start Local Inference

From the repo root:

```bash
bash scripts/start_local_vllm_server.sh
```

Defaults:

- model: `NousResearch/Hermes-3-Llama-3.1-8B`
- endpoint: `http://localhost:8001/v1/chat/completions`
- container: `market_local_vllm_graph`
- GPU memory utilization: `0.85`
- max model length: `4096`
- max concurrent sequences: `512`

Override with environment variables when needed:

```bash
LOCAL_GRAPH_MODEL="Qwen/Qwen2.5-14B-Instruct" \
LOCAL_GRAPH_MAX_MODEL_LEN=4096 \
LOCAL_GRAPH_MAX_NUM_SEQS=256 \
bash scripts/start_local_vllm_server.sh
```

## Monitor Compute Engagement

In a second terminal:

```bash
bash scripts/monitor_local_graph_compute.sh
```

During a real run, `nvidia-smi` should show non-trivial GPU utilization and the extractor should print non-zero `docs/min` and `tokens/sec`.

If GPU utilization remains near zero while extraction is running, the extractor is not reaching vLLM or vLLM is not using the GPU.

## Smoke Test

Run a small benchmark before launching the full corpus:

```bash
POSTGRES_URL="postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db" \
.venv/bin/python scripts/bulk_local_graph_extract.py \
  --site-id d9f940ea-982c-4a04-8c6b-2d653457cf9a \
  --limit 1000 \
  --workers 64 \
  --report-seconds 10
```

What to look for:

- the model probe returns HTTP `200`,
- `docs/min` climbs after the first few batches,
- `tokens/sec` is non-zero,
- GPU utilization is not near zero,
- and the script prints a new `run_id`.

Use that `run_id` to resume the same run:

```bash
.venv/bin/python scripts/bulk_local_graph_extract.py \
  --site-id d9f940ea-982c-4a04-8c6b-2d653457cf9a \
  --run-id <RUN_ID_FROM_SMOKE_TEST> \
  --workers 128
```

The extractor writes a checkpoint file under `.server-state/` so it can resume without reprocessing successful documents.

## Restart And Reboot Behavior

The expensive bulk extractor is checkpointed. If the machine reboots or the process stops, successful document chunks recorded in the checkpoint file should not be reprocessed when the same run is resumed with the same checkpoint.

The durable output is in PostgreSQL:

- raw extracted entities in `graph_entity_facts`,
- raw extracted relationships in `graph_relationship_facts`,
- run and task lineage in the orchestration ledger.

Do not delete a run, reset an existing run, or clear graph fact tables unless the operator explicitly intends to discard that extraction work.

## Full Local Run

After the smoke test proves local compute is engaged:

```bash
POSTGRES_URL="postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db" \
.venv/bin/python scripts/bulk_local_graph_extract.py \
  --site-id d9f940ea-982c-4a04-8c6b-2d653457cf9a \
  --run-id <RUN_ID> \
  --workers 128 \
  --fetch-size 2000 \
  --report-seconds 15
```

Tune `--workers` upward only if:

- vLLM throughput still rises,
- GPU utilization has headroom,
- the model server does not return timeouts,
- and Postgres writes are not lagging behind inference.

## Cloud RunPod Path

Use the same extractor against a cloud vLLM endpoint if local throughput is insufficient.

Required shape:

- vLLM-compatible `/v1/chat/completions` endpoint,
- reachable from this machine,
- same model or a compatible instruct model,
- enough concurrency to beat the local machine.

Example:

```bash
.venv/bin/python scripts/bulk_local_graph_extract.py \
  --site-id d9f940ea-982c-4a04-8c6b-2d653457cf9a \
  --run-id <RUN_ID> \
  --model-url https://<runpod-endpoint>/v1/chat/completions \
  --model <remote-model-id> \
  --workers 256
```

## Finalize The Graph

After extraction has accumulated enough facts, project the run into canonical graph state and Neo4j:

```bash
POSTGRES_URL="postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db" \
NEO4J_URI="bolt://localhost:17687" \
.venv/bin/python scripts/finalize_bulk_graph_run.py \
  --site-id d9f940ea-982c-4a04-8c6b-2d653457cf9a \
  --run-id <RUN_ID> \
  --mark-run-completed
```

By default this runs:

1. canonical entity resolution,
2. canonical entity persistence,
3. canonical relationship aggregation,
4. canonical relationship persistence,
5. canonical entity projection,
6. document mention projection,
7. `INTERACTS_WITH` projection,
8. Louvain community detection,
9. community projection,
10. stale graph pruning.

It does not summarize communities by default because that would reintroduce remote LLM calls.

Optional flags:

- `--summarize-communities`: name and summarize communities with the configured LLM client.
- `--semantic-similarity`: project document similarity edges. This can be expensive on a full run.
- `--publish-ready`: verify projection counts and mark graph ready. Requires `--semantic-similarity`.
- `--no-prune`: leave older Neo4j projection state in place for inspection.
- `--skip-canonical-entities`: resume after canonical entity persistence has already completed.
- `--skip-canonical-relationships`: resume after canonical relationship persistence has already completed.
- `--skip-core-projection`: resume after canonical entity, document mention, and `INTERACTS_WITH` projection have already completed.

## Graph Quality Recovery

If the graph renders as a hairball or misses obvious private equity shops, do not immediately rerun the bulk extractor.

Use the recovery sequence in `docs/architecture/graph-quality-recovery.md`:

1. inspect raw PostgreSQL graph facts for private-equity and oil-and-gas signal,
2. normalize entity types into stable graph categories,
3. improve canonical entity resolution beyond exact normalized-name matching,
4. normalize relationship labels into a strategic vocabulary,
5. add thesis-aware ranking and pruning,
6. rebuild canonical state and Neo4j projection from existing PostgreSQL facts,
7. evaluate targeted graph views before showing the full topology.

A full extraction rerun is justified only if raw `graph_entity_facts` and `graph_relationship_facts` genuinely lack the expected signal. If that happens, run a targeted second pass over high-relevance chunks rather than the full corpus.

## Why This Should Engage Compute

The old bottleneck was not just low concurrency. The bespoke orchestrator made one remote Gemini request per chunk and leased only a few LLM tasks at a time.

The bulk lane changes the shape:

- the model is local or cloud-hosted behind a high-throughput OpenAI-compatible endpoint,
- the extractor keeps many HTTP requests in flight,
- vLLM batches those requests on GPU,
- the script reports real `docs/min` and `tokens/sec`,
- and `nvidia-smi` confirms whether the GPU is doing work.

If those signals are flat, the workflow is not using the machine and should be stopped before a full run.
