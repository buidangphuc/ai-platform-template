# messaging/tasks Specification

## Purpose
Defines how a submitted task reaches a worker and is processed once to a terminal
state: the message contract, who reclaims, the claim rule, and what failure
reporting may expose. Delivery repair (re-announcing queued tasks), the single
dispatch path and the lease bound on handlers are in `messaging/task-delivery`.

## Requirements

### Requirement: One task message contract

Task submission and the reclaim loop SHALL announce a task with a flat message
body containing a non-empty string `task_id`, a non-empty string `type` and, when
known, a non-empty string `request_id`; no other key is allowed. The worker SHALL
parse every received message with that same contract. A message that does not
satisfy it SHALL be rejected without requeue (dead-lettered) and SHALL NOT be
acknowledged.

#### Scenario: Submitted task reaches the worker
- **WHEN** a task is submitted and the worker receives its announcement
- **THEN** the queue message body holds the task's `task_id` and `type` and the worker processes the task

#### Scenario: Malformed message is dead-lettered
- **WHEN** the worker receives a body without `task_id` or `type`, or with any extra key
- **THEN** it nacks the message with `requeue=False` on the first delivery and does not ack it

### Requirement: The worker process owns the reclaim and cleanup loops

While the worker runs, it SHALL periodically requeue PROCESSING tasks whose lease
expired and re-announce stale QUEUED tasks (reclaim loop), and purge expired rows
(cleanup loop). Both loops SHALL stop when the worker shuts down and SHALL
continue after an iteration fails. Multiple worker processes SHALL be able to run
them concurrently without claiming the same row twice.

#### Scenario: Task reaches a terminal state with only the worker running
- **WHEN** a task has been submitted and only the worker is running
- **THEN** the task reaches COMPLETED

#### Scenario: Loops stop with the worker
- **WHEN** the worker is asked to shut down
- **THEN** the reclaim and cleanup loops exit and the process terminates

### Requirement: Reclaimed tasks are announced again, boundedly

Reclaiming SHALL change at most the configured batch size of expired-lease
PROCESSING tasks to QUEUED and SHALL announce each of them to the worker again. A
failed announcement SHALL be logged and repaired by a later re-announcement of
the QUEUED task.

#### Scenario: Crashed worker's task is redelivered
- **WHEN** a task's processing lease expires and the reclaim loop runs
- **THEN** the task is QUEUED and a new task message for it is published

#### Scenario: Batch bound
- **WHEN** more tasks than the batch size have expired leases
- **THEN** one reclaim pass changes only the batch size of them

### Requirement: Claiming a task is compare-and-set

A worker SHALL claim a task by moving it to PROCESSING only from QUEUED, or from
PROCESSING whose lease has expired, and the store SHALL report whether the claim
succeeded. A COMPLETED or FAILED task, or one under a live lease, SHALL NOT be
claimed, and the worker SHALL acknowledge and skip such a message without running
the handler.

#### Scenario: Redelivery of a completed task
- **WHEN** a message for a COMPLETED task is delivered again
- **THEN** the message is acknowledged, the task is unchanged and the completion handler is not called

#### Scenario: Failed task stays failed
- **WHEN** a claim is attempted on a FAILED task
- **THEN** the claim returns false and the task remains FAILED

### Requirement: Failure reports expose no raw exception text

When processing fails, the stored task error SHALL contain only the exception
class name and a generic message; the full exception SHALL be logged by the
worker. A failed task SHALL be terminal, so its message is dead-lettered.

#### Scenario: Handler raises with sensitive text
- **WHEN** the completion handler raises an exception whose message contains a secret
- **THEN** the task is FAILED, its `error` does not contain that text, and the message is nacked without requeue

### Requirement: Reclaim is capped by attempts

Reclaiming an expired-lease PROCESSING task whose `attempts` is at least
`TASKS_MAX_ATTEMPTS` SHALL set it to FAILED with error `max_attempts_exceeded`
and SHALL NOT announce it again. Tasks under the cap SHALL be requeued and
announced as before. One pass SHALL settle at most the batch size of tasks,
failed and requeued together. A FAILED task SHALL NOT be claimable.

#### Scenario: Worker crashes on every attempt
- **WHEN** a task has been claimed `TASKS_MAX_ATTEMPTS` times and its lease expired again
- **THEN** reclaim marks it FAILED with `max_attempts_exceeded`, publishes no new task message, and a later claim returns false

#### Scenario: Task under the cap
- **WHEN** an expired-lease task has fewer attempts than the cap
- **THEN** it is QUEUED and announced again

### Requirement: The worker purges expired tasks and old published outbox events

While the worker runs, it SHALL periodically delete tasks past `expires_at` and,
when the outbox is enabled, outbox events with status published older than
`OUTBOX_RETENTION_SECONDS`. Deletes SHALL be bounded batches that repeat until a
batch is short. Pending and failed outbox events SHALL NOT be deleted. The loop
SHALL stop with the worker and continue after a failed iteration.

#### Scenario: Old published events
- **WHEN** published outbox events older than the retention exist alongside recent published, pending and failed ones
- **THEN** only the old published ones are deleted, at most the batch size per statement

#### Scenario: Backlog larger than a batch
- **WHEN** more expired rows exist than the batch size
- **THEN** one cleanup tick deletes them over several batches
