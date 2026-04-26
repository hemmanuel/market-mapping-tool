# Transition Model

## Principle

Workflow progression must be declarative and inspectable. The orchestrator should not embed business logic in opaque imperative routing.

## Transition Responsibilities

A transition definition should specify:

- source task type,
- source outcome,
- target task type or terminal action,
- payload mapping rules,
- fan-out behavior,
- join or barrier requirements,
- retry policy overrides,
- and failure routing.

## Required Capabilities

### Fan-out

One task may create many downstream tasks, for example:

- market sizing -> bucket discovery tasks,
- planner output -> many search query tasks,
- URL resolution -> many scrape tasks.

### Fan-in or barrier

Some downstream work should wait for a set of sibling tasks or a stage completion condition before continuing.

### Conditional routing

Example:

- relevant scraped source -> chunk and embed,
- irrelevant source -> discard or quarantine.

### Terminal handling

The model must define explicit semantics for:

- success,
- discard,
- retry,
- halt,
- log-and-continue,
- and dead-letter.

## Example Shape

```yaml
task: SCRAPE_SOURCE
on:
  SUCCESS:
    emit:
      - task: BOUNCE_SOURCE
        map:
          raw_text: output.raw_text
          source_url: input.source_url
          storage_object: output.storage_object
  FAILED:
    action: RETRY_OR_DLQ
```

## Rule

If the transition logic only exists inside `if` statements in engine code, the architecture is incomplete.

## Branch Status

The current branch already uses a declarative transition model for the bespoke acquisition path and the current bespoke graph path.

Graph-specific barrier and fan-in support are now present, so the transition model governs document-set stabilization, graph fact extraction, canonical resolution, relationship aggregation, semantic similarity projection, community projection, pruning, and graph-ready publication without falling back to legacy imperative graph logic.

The remaining gap is no longer basic graph transition coverage. What remains is parity validation, richer relationship normalization, and convergence of the last graph-facing UI surfaces on the bespoke outputs already produced by this transition model.
