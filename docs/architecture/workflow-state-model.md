# Workflow State Model

## Principle

The system must separate run-scoped state from task-scoped state. Not every field belongs in every task payload.

## Layers

### Pipeline Run

Represents one execution against a site.

Examples:

- site ID,
- run objective,
- orchestration version,
- start/end timestamps,
- aggregate status.

### Workflow Context

Run-scoped, durable reference data used by many tasks.

Examples:

- niche,
- ontology,
- acquisition policy version,
- tenant and site metadata,
- run configuration.

### Task Frame

A single unit of work with a typed payload and explicit lifecycle state.

Examples:

- discover companies for a bucket,
- resolve URLs for a query,
- scrape a source,
- embed chunk batch,
- project graph updates.

### Task Attempt

One execution attempt of a task frame.

Examples:

- lease start,
- worker version,
- heartbeat timestamps,
- failure metadata,
- exit outcome.

### Artifacts

Durable references to outputs and evidence.

Examples:

- MinIO object key,
- source URL,
- chunk IDs,
- embedding batch ID,
- graph fact batch ID,
- canonical resolution batch ID,
- canonical community batch ID,
- graph-ready publication summary,
- Neo4j projection identifiers.

## Design Rule

If a field is needed by many tasks and does not change per task, it likely belongs in workflow context, not in every payload.

If a field is required to make a worker deterministic, it belongs in the task frame or in a referenced durable context object, not in transient memory.
