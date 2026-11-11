All decisions closed (see `proposal.md`). Packets are ordered; packets inside one wave own disjoint files.

## 1. localinfra profiles (separate PR in `~/Documents/localinfra`)

Owns: `localinfra/compose.yaml`, `localinfra/apps.yaml`, `localinfra/README.md`, provisioning in `localinfra/bin`.

- [ ] 1.1 Add `postgres` profile (`postgres:16-alpine`, host port 15432), per-app database and user
- [ ] 1.2 Add `elasticmq` profile (`softwaremill/elasticmq-native`, host port 19324)
- [ ] 1.3 Add `rabbitmq` profile (`rabbitmq:4-alpine`, the only new image), per-app vhost and user
- [ ] 1.4 Register app `aipt` with its engines; `bin/li verify` passes

## 2. Test infra contract (wave 1)

Owns: `tests/infra.py` (new), `tests/conftest.py`, `pyproject.toml` (markers), `docs/agents/project.md`.

- [ ] 2.1 Fixtures `pg_sessionmaker`, `redis_client`, `mongo_gateway`, `s3_bucket`, `sqs_queue` with per-test isolation; verify `test_infra_isolation` (two tests never see each other's data)
- [ ] 2.2 Marker `infra(...)`: skip when URL missing, fail when `TEST_INFRA_REQUIRED=1`; verify `test_infra_marker_required`
- [ ] 2.3 `alembic upgrade head` once per session on the test database
- [ ] 2.4 `docs/agents/project.md`: replace the env list with `bin/li up core mongo minio postgres elasticmq` + `bin/li env aipt`

## 3. Remove infra emulators (wave 2)

Owns: the 11 emulator files listed in `proposal.md`, `tests/plugins/real_redis.py`, `tests/mongo_fake.py`, `pyproject.toml` dev deps, `uv.lock`.

- [ ] 3.1 Redis tests on `redis_client`; delete `real_redis.py`
- [ ] 3.2 Postgres store and conversations tests on `pg_sessionmaker`; drop the SQLite branches
- [ ] 3.3 Mongo quota tests on `mongo_gateway`; delete `mongo_fake.py`
- [ ] 3.4 Remove `fakeredis`, `aiosqlite`; verify `uv lock` and full suite

## 4. Remove `Fake*` port doubles (wave 2, disjoint from 3)

Owns: `test_application_lifespan.py`, `test_idempotency_http.py`, `test_idempotency_store.py`, `test_outbox.py`, `test_audit.py`, `test_mongo.py`, `objects/test_s3.py`, `queues/test_sqs.py`.

- [ ] 4.1 Lifespan tests open real resources and assert they close
- [ ] 4.2 Failure paths via real infra: closed port, wrong credentials, missing bucket/queue, `docker pause` timeout
- [ ] 4.3 List every failure that could not be reproduced and whose test was dropped (record here)

## 5. Real HTTP server instead of `MockTransport` (wave 2, disjoint)

Owns: `tests/factories.py` (`mock_upstreams` → `local_upstreams`), `test_upstream.py`, `test_model_server_client.py`, `test_webhooks.py`, `tests/unit/core/test_mock_upstreams.py`, `docs/agents/architecture.md` "Testing a feature".

- [ ] 5.1 `local_http_server` fixture: scripted status, delay, connection drop; verify retry, breaker open, request-id, isolation tests pass over real sockets
- [ ] 5.2 `Upstream` keeps no `transport=` test hook if nothing else needs it

## 5b. RabbitMQ real tests (wave 2, disjoint)

Owns: `tests/unit/modules/queues/test_rabbitmq.py` (new), `pyproject.toml` coverage `omit` entry.

- [ ] 5b.1 Marker `infra("rabbitmq")`; publish, consume, ack, nack to dead letter, reconnect after broker restart
- [ ] 5b.2 Remove `app/modules/messaging/queue/adapters/rabbitmq.py` from coverage omit

## 6. Remove in-memory backends from app (wave 3)

Owns: `app/modules/messaging/{queue,tasks}/adapters/memory.py`, `InMemoryRateLimiter`, cache/object/quota/rag memory backends, their factories, `app/core/config/{messaging,platform,ai}.py` literals and defaults, `.env.example`, tests of memory backends, `README.md`, `docs/template-guide.md`, `docs/usage.md`.

- [ ] 6.1 Delete memory adapters and their tests; `*_BACKEND` literals lose `memory`
- [ ] 6.2 New defaults point at the real backend; validators require the matching `*_ENABLED`
- [ ] 6.3 `.env.example` matches `bin/li env aipt`; `scripts/check_env_example` passes
- [ ] 6.4 Eval gate runs with real infra (or only the fake LLM path if it needs none)

## 8. CI and local gate (A′)

Owns: `.github/workflows/test.yml`, `Makefile` (or `scripts/test_infra.sh`), `docs/agents/project.md` `## Checks`.

- [ ] 8.1 CI `pytest -m "not infra"` with `--cov-fail-under=<measured, rounded down>`; no service containers
- [ ] 8.2 `on: push` limited to `branches: [main]`; `pull_request` unchanged
- [ ] 8.3 One local command: `bin/li up` profiles + `TEST_INFRA_REQUIRED=1 pytest --cov-fail-under=80`; listed in `## Checks` so `pre-commit-ci` runs it before every commit/push

## 9. Close

- [ ] 9.1 `grep -rE "fakeredis|aiosqlite|MockTransport|InMemory|class _?Fake" tests app` returns only LLM and Langfuse fakes
- [ ] 9.2 Local command (8.3): 0 skipped except documented ones; coverage ≥ 80 %
- [ ] 9.4 `pytest -m "not infra"` with no service running passes its gate (what CI sees)
- [ ] 9.3 `openspec validate real-infra-tests --strict`
