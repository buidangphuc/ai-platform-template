All decisions closed (see `proposal.md`). Packets are ordered; packets inside one wave own disjoint files.

## 1. localinfra profiles (`~/Documents/localinfra`, local only, no commits there)

Owns: `localinfra/compose.yaml`, `localinfra/apps.yaml`, `localinfra/README.md`, provisioning in `localinfra/bin`.

- [x] 1.1 Add `postgres` profile (host port 15432), per-app database and user; image switched to `pgvector/pgvector:pg16` for RAG, extension `vector` in `template1` and every app DB; `postgres_createdb` flag lets `aipt` create throwaway `aipt_t_*` databases
- [x] 1.2 Add `elasticmq` profile (`softwaremill/elasticmq-native`, pinned by digest, host port 19324)
- [x] 1.3 Add `rabbitmq` profile (`rabbitmq:4-alpine`), per-app vhost and user
- [x] 1.4 Register app `aipt` with its engines; `bin/li verify` passes (31/31)

## 2. Test infra contract (wave 1)

Owns: `tests/infra.py` (new), `tests/conftest.py`, `pyproject.toml` (markers), `docs/agents/project.md`.

- [x] 2.1 Fixtures `pg_url`, `pg_engine`, `pg_sessionmaker`, `redis_prefix`, `redis_client`, `mongo_gateway`, `s3_target`, `sqs_queue`, `rabbitmq_url`, `infra_settings` with per-test isolation; verified in `tests/unit/core/test_infra_contract.py`
- [x] 2.2 `require(engine)`: skip when the URL is missing, fail when `TEST_INFRA_REQUIRED=1`; tests using an infra fixture get the `infra` marker automatically
- [x] 2.3 `alembic upgrade head` once per session on a throwaway database (`alembic/env.py` accepts `config.attributes["database_url"]`)
- [x] 2.4 `docs/agents/project.md` documents `make infra-up` / `make test-infra`; `.env.test` holds the `TEST_*` URLs. `REDIS_USERNAME` setting added for ACL users

## 3. Remove infra emulators (wave 2)

- [x] 3.1 Redis tests on `redis_client`; `tests/plugins/real_redis.py` deleted
- [x] 3.2 Postgres store and conversations tests on `pg_sessionmaker`; SQLite branches dropped
- [x] 3.3 Mongo quota tests on `mongo_gateway`; `tests/mongo_fake.py` deleted
- [x] 3.4 `fakeredis`, `aiosqlite` removed from dev deps (`aiosqlite` stays transitively via `llama-index-core`)

## 4. Remove `Fake*` port doubles (wave 2)

- [x] 4.1 Lifespan tests open real resources and assert closure from the server side (`pg_stat_activity`, Redis client id, Mongo `InvalidOperation`)
- [x] 4.2 Failure paths via real infra: closed port, wrong credentials, foreign bucket, missing queue. Not done: timeouts via `docker pause` (pausing shared Redis/Postgres would stall other apps on localinfra); HTTP timeouts are covered by `local_http_server` delays
- [x] 4.3 Dropped because real infra cannot produce them, and what covers the intent now:
  - SQS `AccessDenied` at open (ElasticMQ has no auth): the "log and continue" branch is deleted, so SQS now requires `sqs:GetQueueAttributes` (spec delta `core/lifecycle-aws-fail-fast`)
  - SQS `InvalidClientTokenId`/`SignatureDoesNotMatch`, S3 `ExpiredToken`: `test_aws_errors.py` asserts they are not treated as permission denials, so `open()` fails fast; S3 wrong key/secret is tested on real MinIO
  - "session `__aexit__` called" spies: no server-side signal for S3/SQS clients
  - SQL-text assertions: replaced by behaviour tests
  - `InMemoryRateLimiter` clock-injected boundary tests: the class is gone

## 5. Real HTTP server instead of `MockTransport` (wave 2)

- [x] 5.1 `local_http_server` (`tests/http_server.py`, raw `asyncio.start_server`): scripted status, delay, connection drop; retry, breaker, timeout, request-id and isolation tested over real sockets; not marked `infra`, runs in CI
- [x] 5.2 `UpstreamClient.from_upstream` has no `transport=` hook; `mock_upstreams` became `local_upstreams`

## 5b. RabbitMQ real tests (wave 2)

- [x] 5b.1 13 tests on a real broker: publish/consume/ack, batching, dead letter on/off, requeue counts, redelivery after close, wrong password, closed port, idempotent close, re-open, argument mismatch, and reconnect after the broker drops every `aipt` connection (`rabbitmqctl close_all_user_connections` via `TEST_RABBITMQ_CONTAINER`; a mutation to non-robust `aio_pika.connect` turns it red). A real `docker restart` was checked once by hand: recovered in 5 s, no message lost
- [x] 5b.2 Adapter bugs fixed: `send()` returns the message id the receiver sees; `close()` before `open()` is a no-op. (The file was never omitted from coverage; the `pyproject.toml` entry is a pyright exclude and stays.)

## 6. Remove in-memory backends from app (wave 3)

- [x] 6.1 Memory adapters and their tests deleted; `*_BACKEND` literals lose `memory`
- [x] 6.2 Defaults point at the real backend; validators require the matching service; every `*_ENABLED` still defaults to false, so the app boots without infra until a capability is enabled
- [x] 6.3 `.env.test` matches `bin/li env aipt`; `scripts/check_env_example` passes
- [x] 6.4 Eval gate passes (fake LLM path, no infra)
- [x] 6.5 RAG: `memory` replaced by Postgres pgvector (`llama-index-vector-stores-postgres`), with `ParameterizedPGVectorStore` binding metadata filters as parameters (upstream interpolates them into SQL)

## 8. CI and local gate (A′)

- [x] 8.1 CI `pytest -m "not infra" --cov-fail-under=74` (measured 74.57 %); no service containers
- [x] 8.2 `on: push` limited to `branches: [main]`; `pull_request` unchanged
- [x] 8.3 `make infra-up` + `make test-infra` (`.env.test`, `--cov-fail-under=80`); listed in `## Checks`; `make ci` runs it

## 7. Nothing untestable left behind

- [x] 7.1 No permanently skipped test: Redis `delete_expired` (a no-op by design) moved out of the shared conformance suite; Redis asserts the native TTL instead, Postgres keeps both `delete_expired` tests with exact counts
- [x] 7.2 Extra-not-installed `skip` guards deleted (dev and CI always install `--all-extras`)
- [x] 7.3 Bugs found by covering the remaining lines on real infra: RabbitMQ `receive(wait_seconds=…)` returned at once on an empty queue (no long-poll: the worker fell back to polling every `poll_interval_seconds`, adding up to one interval of latency); S3 `get`/`exists` turned every `ClientError`, `AccessDenied` included, into "missing". The dead `wait_for(0.05)` loop in RabbitMQ `receive` is gone
- [x] 7.4 SQS ack/dead-letter without `ReceiptHandle`, RabbitMQ nack of an unknown message, S3 without `aioboto3`: tested

- [x] 7.5 `RABBITMQ_QUEUE_TYPE` (`""` = vhost default, `classic`, `quorum`) declares the work queue and DLQ with that type; every RabbitMQ test runs on both types, and on quorum `receive_count` follows the broker's `x-delivery-count` across consumer crashes (classic stops at 2)

## 9. Close

- [x] 9.1 `grep` for emulators and fakes in `tests` finds only LLM, Langfuse and OTel SDK test exporters
- [x] 9.2 `make test-infra`: 810 passed, 1 documented skip (Redis task store `delete_expired`); coverage 96.6 %
- [x] 9.3 `openspec validate real-infra-tests --strict`
- [x] 9.4 `pytest -m "not infra"` with no service running: 539 passed, coverage 74.6 %
