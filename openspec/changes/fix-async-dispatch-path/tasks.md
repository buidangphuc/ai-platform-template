## 1. Message contract and non-retryable signal

Owns: `app/modules/messaging/tasks/message.py`, `app/modules/messaging/queue/worker.py`, `tests/unit/modules/tasks/test_message.py`, `tests/unit/modules/queues/test_polling_worker.py`

- [x] 1.1 `TaskMessage` + `from_body` raising `NonRetryableMessageError`
- [x] 1.2 Worker nacks `NonRetryableMessageError` with `requeue=False`
- [x] 1.3 Verify (red first): `uv run --all-extras pytest -q tests/unit/modules/tasks/test_message.py tests/unit/modules/queues/test_polling_worker.py`

## 2. Task stores: CAS claim and bounded reclaim

Owns: `app/modules/messaging/tasks/{store}.py`, `app/modules/messaging/tasks/adapters/*`, `tests/unit/modules/tasks/{conformance,test_postgres_store}.py`

- [x] 2.1 `mark_processing -> bool` (QUEUED or expired lease) in memory, redis (WATCH/MULTI), postgres
- [x] 2.2 `reclaim_stale_processing -> list[TaskRef]`; Postgres `IN (SELECT ... LIMIT FOR UPDATE SKIP LOCKED) RETURNING`
- [x] 2.3 Verify: `uv run --all-extras pytest -q tests/unit/modules/tasks`; Postgres variant: `TASKS_TEST_POSTGRES_URL=... pytest tests/unit/modules/tasks/test_postgres_store.py`

## 3. Atomic dispatch, relay and reclaim loops

Owns: `app/modules/messaging/tasks/{service,outbox,relay}.py`, `app/modules/messaging/outbox/{adapters,store,publisher}.py`, `app/bootstrap/{resources,worker}.py`, `app/core/config/messaging.py`, `.env.example`, `scripts/run_worker.py`

- [x] 3.1 `TaskDispatcher.submit/reclaim`; `QueueTaskDispatcher(store, queue)`; `PostgresTaskOutboxDispatcher`; `TaskQueueOutboxSink`
- [x] 3.2 Settings validator (`outbox` requires postgres store) + relay/reclaim interval settings mirrored in `.env.example`
- [x] 3.3 `WorkerContext.run()` runs worker + loops; `event_type_prefix` scoping
- [x] 3.4 Worker handler: parse message, CAS skip, safe error, dead-letter on failure
- [x] 3.5 Verify: `uv run --all-extras pytest -q tests/unit tests/integration/test_task_outbox_flow.py`; Postgres variant with `TASKS_TEST_POSTGRES_URL`

## 4. Ops

Owns: `Dockerfile`, `.dockerignore`, `docker-compose.local.yaml`

- [x] 4.1 Copy `scripts/` into the image (and stop `.dockerignore` excluding it; `scripts/smoke/` stays out)
- [x] 4.2 `worker` compose service sharing `x-task-env` with the api
- [x] 4.3 Verify: `docker build -t aipt-test . && docker run --rm aipt-test python -c "import scripts.run_worker"`; `docker compose -f docker-compose.local.yaml config -q`

- Follow-ups (poison-task attempts cap, task/outbox retention loop, redundant quota index) are handled in `openspec/changes/task-outbox-hygiene`.
