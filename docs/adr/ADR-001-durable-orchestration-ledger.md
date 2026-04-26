# ADR-001: Durable Orchestration Ledger

## Status

Accepted

## Decision

The bespoke kernel must use a durable orchestration ledger as the system of record for runs, tasks, attempts, and recovery state.

## Rationale

An in-memory queue cannot provide replay, crash recovery, stuck-task reclamation, or auditability.

## Consequence

Any interim in-memory-only orchestration should be treated as exploratory, not production architecture.
