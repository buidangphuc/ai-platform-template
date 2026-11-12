## Why

The 2026-11-12 audit found capabilities that ship broken or with unsafe defaults. Every clone inherits them, so they are fixed here; where the fix makes a second mechanism redundant, that mechanism is deleted in the same packet.

Findings:

- Tasks can stay QUEUED forever. `QueueTaskDispatcher.submit` (`app/modules/messaging/tasks/service.py:53-54`) creates the row and then sends; a failed send is never repaired. `reclaim` (`:57-61`) commits QUEUED and then sends per task. The outbox path gives up after 3 attempts about 1s apart (`app/modules/messaging/outbox/publisher.py:20,115-117`) and nothing re-drives FAILED events. No sweeper looks at QUEUED (`tasks/adapters/postgres.py:164`).
- A task handler has no time bound (`app/bootstrap/worker.py:128`) and `mark_completed` / `mark_failed` update by id only (`tasks/adapters/postgres.py:126`), so a handler that outlives `TASKS_LEASE_SECONDS` runs twice and the late finisher overwrites the result.
- `LLM_ENABLED=true` with an empty `CHAT_MODEL` serves `"fake response"` with 200 in every environment (`app/modules/ai/llm/router.py:139-145`).
- Default `LLM_TIMEOUT_SECONDS=60` x (`LLM_MAX_RETRIES=1` + 1) exceeds `LLM_CHAIN_DEADLINE_SECONDS=90`; the validator (`app/core/config/ai.py:36-42`) only checks one attempt, so the fallback model is never reached on a hung primary. A first-token stall on the stream path (`llm/runtime.py:241-243`) neither fails over nor counts for the breaker.
- The worker never flushes Langfuse (`app/bootstrap/application.py:96-97,113-118` flushes in the API lifespan only).
- The eval gate always grades the echo handler: `scripts/run_eval.py` builds the feature on an empty `ApplicationResources()`.
- `require_quota` cannot work: `app/bootstrap/addons/quota.py:39` builds the service with no policy and there is no way to register one, so every call raises `KeyError` (500).
- A refunded quota reservation is returned as a success on a retry with the same key (`quota/adapters/postgres.py:258-270`, `quota/adapters/mongo.py:239-249`). Mongo reserve inserts the reservation before charging (`mongo.py:107-136`); refund has no floor (`:173`); `_migrate_active_counters` (`:251-322`) runs on every call, uses the wall clock and has no Postgres equivalent.
- `@idempotent` (`app/modules/platform/idempotency/http.py:128-166`) leaves the key `in_progress` for 600s when the handler raises, replays the unfiltered return value with status 200 whatever the route declares, fails after the side effects for a non-dict body, and ignores the query string in the request hash.
- `POSTGRES_URL` is built by f-string (`app/core/config/infra.py:30-35`): a password containing `@ / : #` yields a wrong host.
- A client `X-Request-ID` is accepted verbatim (`app/core/request_context.py:53-54`) and lands in the access log and task payloads.
- An oversize chunked body returns 400 instead of 413 (`app/core/middleware.py:74-94`). Exclude patterns are substring matches (`:273,345`). The access log sits inside the timeout and rate-limit middlewares and CORS is innermost (`app/bootstrap/middleware.py:20-66`), so 429/504/413 responses are logged wrongly or not at all and carry no CORS headers; preflights consume rate-limit budget.
- The cache cannot return non-UTF-8 bytes: the shared Redis client decodes responses (`app/core/redis.py:14`).
- S3 `list` uses the prefix without a trailing slash and caps silently at 1000 (`app/modules/platform/objects/adapters/s3.py:127-134`).
- `app/core/redaction.py`: the phone pattern rewrites decimals and dates, the `token` marker masks `max_tokens`, a non-string nested key raises.
- `ops/compose/local.yaml` boots with tasks on and no tables, builds without the `ai` extra although the Langfuse overlay needs it, publishes the API on all interfaces with a published default token, and `make docker-build` tags a different image than compose uses.

## What changes

1. Task delivery: the reclaim loop also re-announces QUEUED tasks that were not picked up, which repairs every lost announcement on both task stores. With that in place the outbox dispatch path is redundant and is deleted. **BREAKING**: `TASKS_DISPATCH_BACKEND`, `TASKS_OUTBOX_RELAY_INTERVAL_SECONDS` and `TASKS_OUTBOX_RELAY_BATCH_SIZE` are removed (Settings forbid unknown fields: delete them from `.env`). The generic outbox (`OUTBOX_ENABLED`) is unchanged. A handler is cancelled and the task failed when it reaches the lease; completion and failure are compare-and-set on PROCESSING.
2. LLM: no fake model outside local environments; default `LLM_TIMEOUT_SECONDS` 30 and a validator covering the retry budget; first-token stall fails over; Langfuse is flushed by the LLM addon in both processes; the eval gate grades the real completion service when `LLM_ENABLED`.
3. Quota: `require_quota(policy)` takes the policy; the policy store is deleted; a refunded reservation is charged again on retry; Mongo charges before recording; the Mongo counter migration is deleted. **BREAKING** (Python API): `require_quota(resource, cost)` becomes `require_quota(policy, cost=1)`; `QuotaPolicyStore`, `StaticQuotaPolicyStore` and `build_quota_service(policies=)` are removed.
4. `@idempotent`: releases the key when the handler fails, replays the declared status and the response-model-filtered body, accepts any JSON body, hashes the query string.
5. HTTP edge: escaped `POSTGRES_URL`, validated request id, 413 for chunked bodies, segment-based exclude patterns, access log and CORS outside the short-circuiting middlewares.
6. Storage: binary-safe cache client, slash-terminated S3 list with pagination, redaction fixes.
7. Local stack: migrations run before the API and worker start, the Langfuse overlay builds with the `ai` extra, the API port binds to loopback, one image tag.

## Impact

- Settings removed: `TASKS_DISPATCH_BACKEND`, `TASKS_OUTBOX_RELAY_INTERVAL_SECONDS`, `TASKS_OUTBOX_RELAY_BATCH_SIZE`. Setting added: `TASKS_QUEUED_REANNOUNCE_SECONDS` (default 60). Default changed: `LLM_TIMEOUT_SECONDS` 60 -> 30.
- No migration expected (the sweep uses `tasks.updated_at`); if an index is needed it is revision `0011`.
- Not in this change: conversation history bounds and guards, infra-retry backoff and handler-error retries in the worker, lease clocks, Postgres quota retention, pyright excludes for three adapters, single-value backend settings, migration squash.
