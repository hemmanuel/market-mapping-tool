# ADR-004: Shadow Mode Before Cutover

## Status

Accepted

## Decision

The bespoke kernel must prove parity or improvement in shadow mode before replacing the legacy runtime in live acquisition routes.

## Rationale

The platform cannot trade away acquisition completeness or provenance during migration.

## Consequence

`src/api/routes.py` should only fully cut over after parity checks and recovery semantics are validated.
