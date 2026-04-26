# ADR-003: Declarative Transition Model

## Status

Accepted

## Decision

Workflow progression must be expressed through declarative transition definitions with explicit payload mapping and failure handling semantics.

## Rationale

Imperative routing alone hides workflow meaning inside engine code and makes auditing and replay policy difficult.

## Consequence

The target kernel must move beyond a flat outcome-to-next-task dictionary.
