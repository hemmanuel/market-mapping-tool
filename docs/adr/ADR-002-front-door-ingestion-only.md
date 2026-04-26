# ADR-002: Front-Door Ingestion Only

## Status

Accepted

## Decision

All acquisition, enrichment, backfill, and replay paths must pass through the same ingestion front door.

## Rationale

This preserves source attribution, chunk-level storage, replayability, and consistent graph projection behavior.

## Consequence

Scripts that write only to Neo4j or skip artifact capture are not valid end-state workflows.
