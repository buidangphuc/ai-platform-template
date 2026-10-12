## Why

Two lifecycle audit findings, plus one wiring gap:

- Only the first `CHAT_FALLBACK_MODELS` entry was ever used, and the secondary had no breaker: a failing secondary was retried on every call and a third model could never serve traffic.
- The S3, SQS and RabbitMQ gateways and the webhook dispatcher created their clients lazily (`self._client is None`, `_owns_client`), so bootstrap did not own the connection lifecycle and a misconfigured broker surfaced on the first request, inside a handler.
- `build_health_service` derived checks from resource fields after the fact, so anything not hard-coded there (the model-server client's `ping`) was never registered, and checks ran one after another with no per-check bound.

## What Changes

- `ModelRouter` models an ordered chain per role (`chain(role)`): the `default` chain is `CHAT_MODEL` plus every `CHAT_FALLBACK_MODELS` entry (duplicates dropped), `judge` is its own model alone. Each target in a multi-target chain has its own breaker keyed by (role, target). `LLMInstance.ainvoke` walks the chain, skipping open breakers, moves on only after a transient failure, raises the last error when all fail and `ServiceUnavailableError` when every breaker is open. **BREAKING** for direct router users: `secondary_target`, `fallback_models` and `failover_target` are removed in favour of `chain`, `try_acquire` and the existing `record_*`; `select_target` raises `ServiceUnavailableError` when no target is admitted.
- `S3ObjectGateway`, `SQSQueueGateway`, `RabbitMQQueueGateway` get `async def open(self) -> Self` that connects eagerly; lazy `_get_client` / `_ensure_ready` and their `None` checks are gone, and `close` is unconditional (bootstrap pushes it only after `open` succeeded). RabbitMQ `open` closes its connection if topology declaration fails. `build_queue_gateway` / `build_object_gateway` become `open_queue_gateway` / `open_object_gateway` (async); `_open_queue` is async.
- `HttpWebhookDispatcher` takes a required `httpx.AsyncClient` owned by `WebhookAddon` (closed on the stack); the `post` seam, lazy client, `_owns_client` and `close()` are removed. Tests use `httpx.MockTransport`.
- Readiness checks are registered at open time on `resources.health_checks` (`HealthChecks`, last field of `ApplicationResources`): postgres and redis by their openers, mongo by `MongoAddon`. `ModelServerClient.check()` is a ready-made `DependencyCheck` for a product's own addon to register. `HealthService` runs the checks concurrently, each bounded by the new `HEALTH_CHECK_TIMEOUT_SECONDS` (default 2); a timeout reports `error`. `build_health_service` keeps its signature.

## Capabilities

### New Capabilities
- `ai/llm-fallback-chain`: ordered failover chain with per-target breakers.
- `core/lifecycle-eager-clients`: eager client open owned by bootstrap, health checks registered at open.

### Modified Capabilities
None.

## Impact

- Code: `app/modules/ai/llm/{router,runtime}.py`, `app/modules/platform/objects/{factory,adapters/s3}.py`, `app/modules/messaging/queue/{factory,adapters/sqs,adapters/rabbitmq}.py`, `app/modules/messaging/webhooks/dispatcher.py`, `app/bootstrap/resources.py`, `app/bootstrap/addons/{objects,webhooks,mongo}.py`, `app/core/health.py`, `app/core/config/http.py`, `app/modules/platform/model_server/client.py`, `.env.example`; tests under `tests/unit/`.
- Docs: `.agents/senior-ai-engineer/references/ai-engineering.md` (model selection), `app/core/README.md` (health).
- **Behaviour change, failure timing**: SQS/S3 client creation and the RabbitMQ connect + topology declaration now happen at boot. A broker that is down at startup fails startup (API lifespan and worker) instead of failing the first request. Orchestrators already restart a crash-looping pod; tolerating a down broker at boot would need an explicit retry-at-open, not a lazy first-use connect. SQS/S3 opening only builds the client (aioboto3 does not touch the network until the first call), so bad endpoints or credentials there still surface on first use; RabbitMQ is the backend that genuinely fails at boot. *(Superseded by `aws-fail-fast-and-sqs-dlq`: S3/SQS `open()` now verifies the bucket/queue, so they fail at boot too.)*

## Follow-ups

- The model server has no bootstrap-owned client or setting (the template leaves its URL and lifecycle to the product), so nothing registers `ModelServerClient.check` by default; a product addon does `resources.health_checks.register("model_server", model.check)`.
- `sqs.py`, `rabbitmq.py` and `s3.py` stay excluded from pyright: the optional-import `None` fallbacks still fail type-checking (12 errors with the exclusion lifted).
- Each failover hop can cost a full call timeout; there is no overall deadline across the chain.
