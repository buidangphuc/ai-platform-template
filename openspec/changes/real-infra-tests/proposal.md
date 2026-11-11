## Status

Plan only. No code changes until the open decisions below are closed.

## Why

Policy: only the LLM is faked in tests (cost). Every other dependency runs for real. Today the suite fakes almost everything:

| Kind | Where | Count |
|---|---|---|
| Infra emulators | `fakeredis` (`tests/unit/modules/test_rate_limit.py`, `tasks/test_redis_store.py`, `cache/test_redis.py`, `cache/test_factory.py`, `queues/test_redis_stream.py`), `aiosqlite` standing in for Postgres (`tasks/test_postgres_store.py`, `conversations/test_conversations.py`, `integration/test_task_outbox_flow.py`, `integration/test_conversations.py`), `tests/mongo_fake.py` (`FakeMongoGateway`) | 11 files |
| Hand-written `Fake*` doubles of our own ports | `test_application_lifespan.py` (`_FakeEngine`, `_FakeRedis`, `_FakeQueue`, `_FakeTaskStore`, `_FakeMongoClient`), `test_idempotency_http.py`, `test_idempotency_store.py`, `test_outbox.py`, `test_audit.py`, `test_mongo.py`, `objects/test_s3.py`, `queues/test_sqs.py` | ~10 files |
| `httpx.MockTransport` | `tests/factories.py` (`mock_upstreams`), `test_upstream.py`, `test_model_server_client.py`, `test_webhooks.py` | 4 files |
| In-memory backends **in app code**, default for every capability | `queue/adapters/memory.py`, `tasks/adapters/memory.py`, `InMemoryRateLimiter`, cache/object/quota/rag `memory` backends; defaults in `app/core/config/{messaging,platform,ai}.py` | 7 backends |

The real-infra suite already exists behind env vars and passes against localinfra (2026-11-11: 840 passed, 2 skipped with Postgres 16, Mongo 7, MinIO, ElasticMQ and Redis db 15). The fakes add a second code path that can pass while the real one fails.

## Remote (CI) analysis

Measured 2026-11-11: dropping every test file that needs infra leaves 351 tests and **57 % coverage** (gate is 80 %). Options:

| Option | Coverage in CI | Cost | Risk |
|---|---|---|---|
| A. CI skips infra tests | ~57 %, gate must drop or split | none | Store, queue and migration regressions only caught on a laptop |
| B. GitHub service containers (postgres, redis, mongo, minio, elasticmq, rabbitmq) with the same images as localinfra | same as local (~94 %) | ~1 min startup per run | none beyond CI minutes |
| C. testcontainers in pytest | same as local | image pulls per run, slower | extra dev dependency |

**Decided (D1, 2026-11-11): A′.** B costs 1-2 min per run (mostly the ~1 GB Mongo image) and connection failures already surface at startup (`check_postgres_connection`, `check_redis_connection` in `app/bootstrap/resources.py`, `/readyz`). A′:

- CI runs only tests without `@pytest.mark.infra`, with its own coverage gate (set to the measured value after phase 3-6, rounded down; ~55 % estimated).
- Infra tests run on the developer machine against localinfra (already running, no startup cost) with `TEST_INFRA_REQUIRED=1` and the full 80 % gate, through one documented command used by `pre-commit-ci`.
- Accepted risk: a store, migration or queue bug reaches `main` if the committer skipped the local run.
- Also: `on: push` limited to `main` so a PR push no longer runs the workflow twice.

## What changes

1. **All capabilities stay (D2):** this is a platform template; forks pick capabilities, so "production does not use it" is not a reason to delete. Every module's tests move to real infra.
2. **Test infra contract:** one `tests/infra.py` reads `TEST_POSTGRES_URL`, `TEST_REDIS_URL`, `TEST_MONGO_URI`, `TEST_S3_ENDPOINT_URL`, `TEST_SQS_ENDPOINT_URL`, `TEST_RABBITMQ_URL`; a marker `@pytest.mark.infra("postgres", ...)` skips when the URL is missing (CI per D1) and **fails** when `TEST_INFRA_REQUIRED=1` (local and, under B, CI). Per-test isolation: Postgres schema per worker + truncate, Redis key prefix `aipt:test:<uuid>:` (localinfra forbids FLUSHDB for app users), Mongo db per test, bucket and queue per test.
3. **Delete infra emulators:** `fakeredis`, `aiosqlite` dev deps, `tests/plugins/real_redis.py`, `tests/mongo_fake.py`; every caller moves to the real fixture.
4. **Delete `Fake*` doubles of our ports:** tests go through the real adapter. Failure paths use real infra in a failing state: closed port, wrong password, missing bucket or queue, container paused (`docker pause`) for timeouts. Failures that cannot be produced this way lose their test and are listed in `tasks.md` 4.x.
5. **Delete `httpx.MockTransport`:** a real local HTTP server fixture (`uvicorn` on an ephemeral port, scripted responses: status, delay, drop) for `Upstream`, `ModelServerClient`, webhooks; `mock_upstreams` becomes `local_upstreams`.
6. **Delete in-memory backends from app code:** queue, task store, rate limit, cache, object, quota, rag `memory` options go away; defaults become the real backend. **BREAKING:** the app no longer boots with core dependencies only; `.env.example` points at localinfra; the "core-deps-only `import main`" check changes to "import only, no boot".
7. **Langfuse is out of scope (D3):** the long-term direction is one shared LLM observability layer outside business code; this change does not touch it. Langfuse is treated like the LLM in tests: its fakes stay.
8. **RabbitMQ tested for real (D4):** the adapter loses its coverage omit in `pyproject.toml` and gets real-broker tests (publish, consume, ack, dead letter).
9. **localinfra (shared repo, separate PR there):** add profiles `postgres` (`postgres:16-alpine`, already on disk), `elasticmq` (`softwaremill/elasticmq-native`, already on disk), `rabbitmq` (no image on disk: pull exactly one, `rabbitmq:4-alpine`); register app `aipt` in `apps.yaml` with engines `[postgres, redis, mongo, minio, rabbitmq]`.

## Decisions (2026-11-11)

- **D1 CI:** A′.
- **D2 Capabilities:** keep all; it is a template.
- **D3 Langfuse:** out of scope; fakes stay.
- **D4 RabbitMQ:** real broker tests.

No open decision blocks implementation.

## Impact

- Tests: ~25 files rewritten, 1 plugin + 1 fake module deleted; suite needs localinfra running.
- App: 7 `memory` backends and their settings values removed; `Settings` defaults change; `.env.example` changes.
- Dev deps removed: `fakeredis`, `aiosqlite`.
- CI: `.github/workflows/test.yml` runs `-m "not infra"` with a split coverage gate; `push` only on `main`.
- Docs: `docs/agents/project.md` (test infra section replaces the env list), `docs/template-guide.md`, `docs/usage.md`, `README.md` quick start.
- Shared repo `localinfra`: new profiles and app entry (reviewed by its owners).
