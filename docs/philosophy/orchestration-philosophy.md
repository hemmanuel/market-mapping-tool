# Orchestration Philosophy

## Why the Rewrite Exists

The bespoke orchestration kernel is not a cosmetic refactor. It exists because the platform needs stronger guarantees than a happy-path state graph can provide.

The target orchestration model must be:

- durable,
- explicit,
- replayable,
- idempotent,
- observable,
- and biased toward exhaustive acquisition.

## Core Doctrine

### Durable by default

No critical workflow state should exist only in memory. Every meaningful unit of work must be reconstructible from durable records.

### Explicit contracts over implicit state

Workers should consume typed inputs and produce typed outputs. Hidden mutation of a shared global state object is not acceptable for the target system.

### Front-door acquisition only

If a workflow results in new business knowledge, it must come through the acquisition path that can preserve binaries, text, embeddings, provenance, and graph projections together.

### Idempotent side effects

Every write path must tolerate retries and replay. The system must assume that any task may run more than once.

### Observability is a feature

Operators and users should be able to answer:

- what is running,
- what failed,
- what is waiting,
- what was retried,
- what evidence was acquired,
- and what remains to be done.

### No happy-path assumptions

The design must assume:

- provider rate limits,
- intermittent network failures,
- partial source acquisition,
- process crashes,
- stale leases,
- poisoned tasks,
- and replay after interruption.

## Definition of Performance

Performance means maximum useful work per unit time while preserving:

- correctness,
- provenance,
- recoverability,
- and full-fidelity storage boundaries.

Any optimization that weakens those properties is not a valid optimization.
