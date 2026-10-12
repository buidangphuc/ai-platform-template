## Purpose

Defines how a submitted task reaches a worker and is processed exactly once to a
terminal state: the message contract, atomic dispatch, who relays and reclaims,
the claim rule, and what failure reporting may expose.

## ADDED Requirements

### Requirement: One task message contract

Every dispatcher SHALL announce a task with a flat message body containing
exactly a non-empty string `task_id` and a non-empty string `type`. The worker
SHALL parse every received message with that same contract. A message that does
not satisfy it SHALL be rejected without requeue (dead-lettered) and SHALL NOT be
acknowledged.

#### Scenario: Outbox-dispatched task reaches the worker
- **WHEN** a task is submitted with outbox dispatch and the relay publishes its event
- **THEN** the queue message body equals `{"task_id": <id>, "type": <type>}` and the worker processes the task

#### Scenario: Malformed message is dead-lettered
- **WHEN** the worker receives a body without `task_id` or `type`, or with the old outbox envelope
- **THEN** it nacks the message with `requeue=False` on the first delivery and does not ack it

### Requirement: Outbox dispatch is atomic with task creation

With `TASKS_DISPATCH_BACKEND=outbox`, the task row and its outbox event SHALL be
written in a single database transaction, so a task exists if and only if its
announcement will be published. Settings SHALL reject `outbox` dispatch with a
task store other than Postgres.

#### Scenario: Outbox write fails
- **WHEN** inserting the outbox event fails during submit
- **THEN** no task row exists afterwards

#### Scenario: Unsupported store combination
- **WHEN** settings combine `TASKS_DISPATCH_BACKEND=outbox` with `TASK_STORE_BACKEND` of `memory` or `redis`
- **THEN** settings validation fails naming the required Postgres task store

### Requirement: The worker process owns the relay and the reclaim loop

While the worker runs, it SHALL publish pending `task.*` outbox events to the work
queue (only when dispatch is `outbox`) and SHALL periodically requeue PROCESSING
tasks whose lease expired. Both loops SHALL stop when the worker shuts down and
SHALL continue after an iteration fails. Multiple worker processes SHALL be able
to run them concurrently without claiming the same row twice.

#### Scenario: Pending event is published without any other process
- **WHEN** a task has been submitted with outbox dispatch and only the worker is running
- **THEN** the task is delivered to the queue and reaches COMPLETED

#### Scenario: Loops stop with the worker
- **WHEN** the worker is asked to shut down
- **THEN** the relay and reclaim loops exit and the process terminates

### Requirement: Reclaimed tasks are announced again, boundedly

Reclaiming SHALL change at most the configured batch size of expired-lease
PROCESSING tasks to QUEUED and SHALL announce each of them to the worker again;
with outbox dispatch the status change and the new outbox event SHALL commit in
one transaction.

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
