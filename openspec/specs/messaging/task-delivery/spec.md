# messaging/task-delivery Specification

## Purpose
How async tasks reach a worker at least once, how lost announcements are repaired, and how a handler is bounded by its lease.

## Requirements

### Requirement: A queued task is always announced again

The reclaim loop SHALL, on every tick and for both task stores, re-announce tasks that are QUEUED and whose `updated_at` is older than `TASKS_QUEUED_REANNOUNCE_SECONDS`, up to `TASKS_RECLAIM_BATCH_SIZE`, and SHALL bump their `updated_at` so each task is re-announced at most once per interval. Tasks past `expires_at` SHALL NOT be re-announced.

#### Scenario: Send fails at submit
- **WHEN** `submit` stores the task and the queue send raises
- **THEN** the task stays QUEUED and the next reclaim tick after the interval sends its message

#### Scenario: Send fails after reclaim
- **WHEN** a stale PROCESSING task is put back to QUEUED and its send raises
- **THEN** a later reclaim tick announces it

#### Scenario: Duplicate announcement is harmless
- **WHEN** a re-announced task is delivered twice
- **THEN** it runs once (the second `mark_processing` returns false)

#### Scenario: Fresh tasks are left alone
- **WHEN** a task was queued less than the interval ago
- **THEN** the sweep does not announce it

#### Scenario: One re-announcement per interval
- **WHEN** two reclaim ticks run within one interval
- **THEN** a stale queued task is announced by the first tick only

### Requirement: Tasks have one dispatch path

Task submission SHALL be "store the row, then send"; `TASKS_DISPATCH_BACKEND`, the task outbox dispatcher, the task outbox sink and the outbox relay loop SHALL NOT exist. The generic outbox capability (`OUTBOX_ENABLED`, store, publisher, sinks, retention cleanup) SHALL be unchanged.

#### Scenario: Removed setting is rejected
- **WHEN** `TASKS_DISPATCH_BACKEND` is set
- **THEN** `Settings` fails validation as for any unknown field

#### Scenario: Worker loops
- **WHEN** the worker starts with tasks enabled
- **THEN** it runs the reclaim loop and the cleanup loop and no relay loop

### Requirement: A handler cannot outlive its lease

The worker SHALL run each handler under a timeout of `TASKS_LEASE_SECONDS`; on timeout the handler is cancelled, the task is marked FAILED with an error naming the lease, and the message is dead-lettered like any failed task.

#### Scenario: Handler exceeds the lease
- **WHEN** a handler runs longer than the lease
- **THEN** it is cancelled, the task is FAILED, and no second worker runs it

### Requirement: Completion is compare-and-set

`mark_completed` and `mark_failed` SHALL change a task only while it is PROCESSING and SHALL return whether they did, on both stores. The worker SHALL log and drop a result that was not applied.

#### Scenario: Late finisher
- **WHEN** a task was already settled (COMPLETED or FAILED) and a second `mark_completed` arrives
- **THEN** the stored status, result and error are unchanged and the call returns false

#### Scenario: Redis update is atomic
- **WHEN** two settlements race on the Redis store
- **THEN** exactly one is applied
