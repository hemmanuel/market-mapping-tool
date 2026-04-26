# Recover Stuck Tasks

## Goal

Reclaim tasks whose workers died or stopped heartbeating.

## Expected Signals

- expired lease,
- stale heartbeat,
- excessive attempt age,
- or queue starvation around a task partition.

## Expected Procedure

1. Identify stale leased tasks.
2. Verify no healthy worker still owns the lease.
3. Mark the attempt as abandoned.
4. Return the task to available state or move it to dead-letter based on policy.
