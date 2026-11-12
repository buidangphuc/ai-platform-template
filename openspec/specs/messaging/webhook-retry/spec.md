# messaging/webhook-retry Specification

## Purpose
How webhook dispatch retries transient failures and how callers that own their retries send once.

## Requirements

### Requirement: Webhook dispatch retries transient failures

`HttpWebhookDispatcher.dispatch(url, envelope)` SHALL retry according to its `RetryPolicy` (default `DEFAULT_WEBHOOK_RETRY_POLICY`, attempts from `WEBHOOK_MAX_ATTEMPTS`) and return the `WebhookDeliveryResult` of the last attempt. Each attempt SHALL be signed with its own timestamp. The wait between attempts SHALL go through an injectable `sleep`.

#### Scenario: Transient status then success
- **WHEN** the endpoint answers 503 and then 200
- **THEN** `dispatch` returns a succeeded result and the endpoint received two requests

#### Scenario: Non-retryable status
- **WHEN** the endpoint answers 400
- **THEN** `dispatch` returns status 400 after exactly one request

#### Scenario: Attempts exhausted
- **WHEN** the endpoint answers 503 on every request and the policy allows 3 attempts
- **THEN** `dispatch` returns status 503 after exactly three requests

#### Scenario: Transport error and timeout are retried
- **WHEN** the connection is refused or the attempt times out
- **THEN** the attempt is retried up to the policy's attempts and the last result carries the error text

#### Scenario: Numeric Retry-After
- **WHEN** a 429 response carries `Retry-After: 2`
- **THEN** the wait before the next attempt is at least 2 seconds and at most the policy's `max_delay_seconds`

### Requirement: Single attempt for callers that own retries

`HttpWebhookDispatcher.send_once(url, envelope)` SHALL make exactly one signed request. `WebhookOutboxSink` SHALL use `send_once`, so an outbox event is retried only by the outbox publisher.

#### Scenario: Outbox sink does not multiply attempts
- **WHEN** the outbox publisher publishes one event to an endpoint that answers 503
- **THEN** the endpoint receives one request per publisher attempt

### Requirement: Retry policy has one error filter

`RetryPolicy` SHALL decide whether an exception is retryable with `retry_on` alone.

#### Scenario: Filter rejects the error
- **WHEN** `retry_on` returns false for an error
- **THEN** `decision(...)` says do not retry

#### Scenario: Error retry-after hint still honoured
- **WHEN** a retryable error carries a retry-after hint
- **THEN** `decision(...)` uses it for the next delay exactly as before
