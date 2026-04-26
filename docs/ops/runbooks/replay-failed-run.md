# Replay Failed Run

## Goal

Recover a failed run without inventing a custom one-off script.

## Required Data

- run ID
- failing task types
- last error class
- artifact state already persisted

## Expected Procedure

1. Identify whether failure occurred before or after source persistence.
2. Confirm the replay scope: full run, task subset, or projection-only rebuild.
3. Requeue the appropriate durable task frames.
4. Preserve auditability by linking replay work to the original run.
