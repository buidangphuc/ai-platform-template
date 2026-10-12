## Why

The async task path (submit -> dispatch -> worker) did not work end to end:

1. **Outbox dispatch never delivered.** `OutboxTaskDispatcher` enqueued
   `{"task_id", "type"}`, but the outbox sink published an envelope
   `{"id", "type", "payload": {...}, "metadata"}`. The worker read a top-level
   `task_id`, found none, logged and returned, which acks the message: every
   outbox-dispatched task was silently dropped.
2. **Nothing ran `OutboxPublisher.publish_pending`** outside tests.
3. **Not atomic.** `TaskService.submit` created the task and enqueued the outbox
   event in two separate transactions, although the docstring claimed one.
4. **Stuck tasks.** `reclaim_stale_processing` had no caller, and only flipped
   status back to QUEUED without announcing the task again.
5. **No consumer-side dedup.** `mark_processing` was unconditional: a redelivered
   COMPLETED task re-ran the LLM and a FAILED task could move back to PROCESSING.
6. **Raw exception text** was stored by `mark_failed` and returned by the API.
7. **Ops.** The image did not contain `scripts/` (so `python -m scripts.run_worker`
   could not start), and compose had no worker.

## What Changes

- **One message contract.** `TaskMessage(task_id, type)` in
  `tasks/message.py`. Both dispatchers publish `TaskMessage.to_body()` (a flat
  body); the worker parses with `TaskMessage.from_body`. A malformed body raises
  the new `NonRetryableMessageError` (in `queue/worker.py`); `AsyncPollingWorker`
  nacks it with `requeue=False` on the first delivery, so it reaches the
  dead-letter destination instead of being acked.
- **Dispatchers own create + announce.** `TaskDispatcher` is now
  `submit(task)` / `reclaim(now, limit)`. `QueueTaskDispatcher(store, queue)`
  creates then sends (documented as non-atomic). The new
  `PostgresTaskOutboxDispatcher(sessionmaker)` inserts the task row and the
  `task.<type>` outbox event in **one** `session.begin()`, and does the same for
  reclaim (state flip + re-announce commit together). `OutboxTaskDispatcher` is
  removed.
- **Settings reject what cannot be atomic.** `TASKS_DISPATCH_BACKEND=outbox`
  requires `TASK_STORE_BACKEND=postgres` (validator in
  `app/core/config/messaging.py`). Correctness over options: a memory/redis task
  store cannot share a transaction with the Postgres outbox.
- **Relay owner: the worker process.** `WorkerContext.run()` runs the polling
  worker plus background loops in one `TaskGroup`:
  `run_outbox_relay` (only for `outbox` dispatch) and `run_reclaim_loop` (always).
  The loops stop when the worker stops (SIGTERM/SIGINT). New settings:
  `TASKS_OUTBOX_RELAY_INTERVAL_SECONDS`, `TASKS_OUTBOX_RELAY_BATCH_SIZE`,
  `TASKS_RECLAIM_INTERVAL_SECONDS`, `TASKS_RECLAIM_BATCH_SIZE`.
  *Why not a separate `scripts/run_outbox_relay.py`:* the relay needs the same
  resource graph (sessionmaker, outbox store, queue) as the worker, the worker is
  already the single long-lived process that owns the queue lifecycle, and a
  second process is one more thing to deploy, scale and forget. Several worker
  replicas are safe: `claim_pending` and the reclaim UPDATE both use
  `FOR UPDATE SKIP LOCKED`. The publisher is scoped to `task.` events
  (`event_type_prefix`) so it never pushes unrelated outbox events into the
  work queue.
- **Bounded reclaim.** The Postgres reclaim is
  `UPDATE ... WHERE id IN (SELECT ... LIMIT n FOR UPDATE SKIP LOCKED) RETURNING id, type`.
  Stores return the reclaimed `TaskRef`s so the dispatcher can announce them.
- **CAS claim.** `TaskStore.mark_processing(task_id, lease_seconds, now=None) -> bool`
  succeeds only from QUEUED, or from PROCESSING whose lease expired; otherwise it
  changes nothing and returns `False`. Implemented in memory (under its lock),
  Redis (`WATCH`/`MULTI`) and Postgres (conditional `UPDATE`), covered by the
  shared conformance suite. The worker acks and skips when it did not claim.
- **Failure handling.** The worker stores `"<ExceptionClass>: task failed (see
  worker logs)"`; the full exception stays in the logs. A failed task is terminal,
  so the worker then raises `NonRetryableMessageError` (dead-letter) instead of
  requeueing a message the CAS would skip anyway. `mark_completed` is no longer
  inside the `try`, so a failed result write cannot flip a finished task to FAILED.
- **Ops.** `Dockerfile` copies `scripts/`; `docker-compose.local.yaml` gains a
  `worker` service (same image) and an `x-task-env` block shared with the api
  (Postgres store + outbox dispatch + Redis queue); `make worker` already existed.

## Capabilities

### New Capabilities

- `messaging/tasks`: task message contract, dispatch atomicity, relay and
  reclaim ownership, claim semantics, failure reporting.

### Modified Capabilities

None.

## Impact

- Code: `app/modules/messaging/tasks/**` (new `message.py`, `outbox.py`,
  `relay.py`; changed `service.py`, `store.py`, adapters),
  `app/modules/messaging/outbox/{adapters,store,publisher}.py` (row builder,
  `event_type_prefix`), `app/modules/messaging/queue/worker.py`,
  `app/bootstrap/{resources,worker}.py`, `app/core/config/messaging.py`,
  `.env.example`, `scripts/run_worker.py`, `Dockerfile`,
  `docker-compose.local.yaml`.
- Behavior: `TASKS_DISPATCH_BACKEND=outbox` with a non-Postgres task store now
  fails at settings validation. A FAILED task's message is dead-lettered on the
  first failure instead of being redelivered up to `WORKER_MAX_ATTEMPTS`.
  `TaskStore.mark_processing` now returns `bool` and
  `reclaim_stale_processing` returns `list[TaskRef]`.
- Operations: run `make migrate` before starting the compose stack (tasks and
  outbox tables). In-flight outbox events written by the old dispatcher (nested
  `{"payload": ...}` envelope is gone, but their payload `{"task_id","type"}` is
  already the new body) are delivered correctly by the new relay.
- Not done (out of scope): a cap on reclaim cycles for a task that crashes its
  worker every time (`attempts` grows, no terminal state); purging published
  outbox rows.
- Unverified: RabbitMQ/SQS/Redis queue backends with the dead-letter path of the
  new non-retryable signal (exercised only with the memory queue and a fake
  gateway; the nack contract itself is the existing one).
