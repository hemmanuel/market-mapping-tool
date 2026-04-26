# Performance Model

## Definition

Performance means maximum completed, source-preserving, replay-safe work per unit time.

It does not mean minimizing calls, minimizing storage, or skipping durable steps.

## Concurrency Classes

The kernel should treat these as separate resource classes:

- LLM generation
- external search/query APIs
- web and binary acquisition
- chunking and preprocessing
- embedding generation
- graph projection writes
- UI/outbox publication

Each class should have its own concurrency controls and backpressure rules.

## Throughput Strategy

### Parallelize independent work

- micro-bucket discovery can fan out,
- company source planning can fan out,
- source scraping can fan out,
- chunk embedding can batch.

### Preserve ordering where meaning matters

- artifact persistence before projection,
- durable attempt recording before retry,
- and outbox/event publication after state mutation.

### Reuse evidence aggressively

- deduplicate already-acquired URLs,
- avoid repeated binary downloads when the artifact already exists,
- replay projections without reacquiring sources when allowed by policy.

## Backpressure Rules

- provider rate limits must be handled with retries and concurrency tuning,
- long-running tasks require leases and heartbeats,
- and saturated classes should slow locally rather than corrupt global state.

## Measurement

The system should eventually measure at least:

- queue depth per task type,
- age of oldest available task,
- task latency by worker,
- retries by error class,
- source acquisition yield,
- chunk and embedding throughput,
- and projection lag.
