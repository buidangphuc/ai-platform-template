## ADDED Requirements

### Requirement: Infra clients open eagerly under bootstrap
The S3, SQS and RabbitMQ gateways SHALL expose `async def open() -> Self` that creates the client (RabbitMQ: connects and declares topology) and SHALL NOT create clients lazily on first use. Bootstrap SHALL call `open` where it builds them and register `close` on the exit stack only after `open` succeeded.

#### Scenario: Broker down at boot
- **WHEN** `QUEUE_BACKEND=rabbitmq` and the broker is unreachable
- **THEN** opening the application resources raises and startup fails

#### Scenario: Failed topology declaration
- **WHEN** RabbitMQ `open` fails after the connection was established
- **THEN** the connection is closed before the error propagates

### Requirement: The webhook dispatcher uses a bootstrap-owned HTTP client
`HttpWebhookDispatcher` SHALL require an `httpx.AsyncClient`, never create or close one, and `WebhookAddon` SHALL create the client and close it on the exit stack.

#### Scenario: Shutdown
- **WHEN** the application resources close
- **THEN** the webhook HTTP client is closed

### Requirement: Readiness checks register at open time
Each opener SHALL register its readiness check on `resources.health_checks` when its resource opens (postgres, redis, mongo). A resource that is not opened SHALL have no check. `HealthService` SHALL run all checks concurrently, each bounded by `HEALTH_CHECK_TIMEOUT_SECONDS`, reporting `error` for a check that raises or times out.

#### Scenario: Hung dependency
- **WHEN** one check hangs past the timeout
- **THEN** it reports `error` and the other checks still report their own result within about one timeout

#### Scenario: Disabled resource
- **WHEN** redis is not enabled
- **THEN** no redis check is registered
