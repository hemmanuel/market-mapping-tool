# Contracts

The kernel is contract-first.

Runtime behavior should be explainable through:

- task frame shape,
- worker input and output schemas,
- transition definitions,
- event types,
- and artifact references.

This directory is the canonical home for those contracts at the documentation layer.

## Required Contract Areas

- `task-frame.md`
- `worker-catalog.md`
- `event-catalog.md`

As the kernel matures, these docs should either be generated from code or verified against code in CI.
