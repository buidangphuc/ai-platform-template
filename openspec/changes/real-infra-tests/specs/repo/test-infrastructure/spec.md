## ADDED Requirements

### Requirement: Only the LLM and Langfuse are faked in tests

Tests SHALL exercise Postgres, Redis, Mongo, S3, SQS, RabbitMQ and outbound HTTP through real services. Only LLM chat models and the Langfuse client MAY be replaced by fakes.

#### Scenario: No infra emulator in the test tree
- **WHEN** the test tree is searched for `fakeredis`, `aiosqlite`, `MockTransport` or a `Fake*` class
- **THEN** only LLM and Langfuse fakes are found

#### Scenario: RabbitMQ adapter is tested
- **WHEN** coverage is measured with `TEST_INFRA_REQUIRED=1`
- **THEN** `app/modules/messaging/queue/adapters/rabbitmq.py` is measured, not omitted

#### Scenario: Store tests hit the real engine
- **WHEN** a Postgres store test runs
- **THEN** it uses the Postgres instance from `TEST_POSTGRES_URL` with the schema produced by `alembic upgrade head`

### Requirement: Infra-backed tests declare what they need

Every test that needs a service SHALL carry `@pytest.mark.infra(<engines>)`. A missing service SHALL skip the test unless `TEST_INFRA_REQUIRED=1`, in which case it SHALL fail.

#### Scenario: Required infra missing
- **WHEN** `TEST_INFRA_REQUIRED=1` and `TEST_REDIS_URL` is unset
- **THEN** every test marked `infra("redis")` fails with a message naming the variable

#### Scenario: Optional infra missing
- **WHEN** `TEST_INFRA_REQUIRED` is unset and `TEST_REDIS_URL` is unset
- **THEN** those tests are skipped and the rest of the suite runs

### Requirement: Tests are isolated on shared infra

Tests SHALL NOT read or delete data outside their own namespace on a shared localinfra instance.

#### Scenario: Redis namespace
- **WHEN** a Redis-backed test runs on localinfra
- **THEN** every key it writes starts with its own `aipt:test:<id>:` prefix and it never issues `FLUSHDB`

#### Scenario: Parallel tests
- **WHEN** two tests write the same logical record
- **THEN** neither sees the other's data

### Requirement: App has no in-memory infrastructure backends

Queue, task store, rate limit, cache, object, quota and RAG settings SHALL NOT offer a `memory` backend.

#### Scenario: Memory backend rejected
- **WHEN** `QUEUE_BACKEND=memory` is set
- **THEN** `Settings` validation fails
