# core/settings-summary Specification

## Purpose
Which settings values are masked in the redacted summary and when the API and the worker log it.

## Requirements

### Requirement: Settings summary masks secrets and nothing else

`Settings.redacted_summary()` SHALL return every field of `model_dump(mode="json")`. A value SHALL be replaced by `"***"` when it is a non-empty string and either (a) one of the underscore-separated words of the field name is `PASSWORD`, `SECRET`, `TOKEN`, `KEY`, `KEYS` or `PEPPER`, or (b) the value is a URL whose authority part contains userinfo (text before an `@` between `://` and the host), whatever the field name. Every other value SHALL be returned unchanged.

#### Scenario: Secrets are masked
- **WHEN** `POSTGRES_PASSWORD`, `AUTH_API_KEYS`, `WEBHOOK_SIGNING_SECRET` and `LANGFUSE_SECRET_KEY` are set
- **THEN** each is `"***"` in the summary

#### Scenario: Credentials inside a URL or URI
- **WHEN** `MONGODB_URI` and `RABBITMQ_URL` each carry a user and a password in their authority part
- **THEN** both are `"***"`, and the computed `POSTGRES_URL` is `"***"`

#### Scenario: Non-secrets are shown
- **WHEN** the summary is built from default settings
- **THEN** `LLM_MAX_TOKENS`, `IDEMPOTENCY_KEY_MAX_LENGTH`, `STREAM_FIRST_TOKEN_TIMEOUT_SECONDS` and a `MONGODB_URI` without credentials keep their real values

#### Scenario: Empty secret stays empty
- **WHEN** `WEBHOOK_SIGNING_SECRET` is `""`
- **THEN** the summary shows `""`

### Requirement: Processes log the summary once at start

The API SHALL log the summary once when its lifespan starts with `init_resources=True`, and the worker entry point SHALL log it once before opening `worker_context`. The line SHALL be at INFO and start with `settings `.

#### Scenario: API start
- **WHEN** the app lifespan starts with a secret configured
- **THEN** one `settings ` line is logged and it does not contain the secret value

#### Scenario: Lifespan without resources
- **WHEN** the lifespan starts with `init_resources=False`
- **THEN** no `settings ` line is logged

#### Scenario: Worker start
- **WHEN** `scripts.run_worker` starts
- **THEN** one `settings ` line is logged before the worker context opens
