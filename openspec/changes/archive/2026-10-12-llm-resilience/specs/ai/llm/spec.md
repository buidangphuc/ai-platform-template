## ADDED Requirements

### Requirement: Transient failures are classified once
Retry and failover SHALL treat a failure as transient only when it is HTTP 408, 429 or 5xx, a timeout, or a connection error. Every other failure (other 4xx, validation or unknown errors) SHALL be deterministic: not retried and not counted by the circuit breaker.

#### Scenario: Deterministic 4xx
- **WHEN** the primary model fails with 400, 401, 413 or 422
- **THEN** the breaker does not count it and no failover happens

#### Scenario: Timeout
- **WHEN** the primary model call times out or the connection fails
- **THEN** the breaker counts it as a failure

### Requirement: Circuit breaker recovers through a single probe
The breaker SHALL open after the configured number of consecutive transient failures, reject calls until the cooldown has passed, then admit exactly one probe call. A successful probe SHALL close it; a transient probe failure SHALL reopen it with a fresh cooldown. A probe that is never reported SHALL be re-granted after one cooldown.

#### Scenario: Probe after cooldown
- **WHEN** the breaker is open and the cooldown has elapsed
- **THEN** one call is admitted to the primary and concurrent calls still use the secondary

#### Scenario: Probe succeeds
- **WHEN** the probe call succeeds
- **THEN** the breaker closes and the primary serves all calls again

### Requirement: The LLM instance resolves the model per call
`LLMInstance` SHALL hold the `ModelRouter` and expose `ainvoke`, which selects the target, applies the tracker's trace config, reports success or error to the router and, after a transient primary failure with a secondary configured, retries once on the secondary. Deterministic errors SHALL propagate without failover. With no model configured the instance SHALL use a fake model.

#### Scenario: Primary overloaded
- **WHEN** `ainvoke` hits a 503 from the primary and a secondary is configured
- **THEN** the call is answered by the secondary and the breaker records one failure

#### Scenario: Bad prompt
- **WHEN** `ainvoke` hits a 400 from the primary
- **THEN** the error propagates and the breaker is unchanged

### Requirement: Provider calls are bounded
Models SHALL be built with `max_tokens`, `timeout` and `max_retries` taken from `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS` and `LLM_MAX_RETRIES`, each range-checked, with `LLM_MAX_RETRIES` defaulting to 1.

#### Scenario: Builder arguments
- **WHEN** the default model builder constructs a model
- **THEN** `init_chat_model` receives the three configured values

### Requirement: The judge model is not silently the production model
When `JUDGE_CHAT_MODEL` is empty and `CHAT_MODEL` is set, resolving the judge target SHALL raise `ValueError` outside local environments (dev, local, test) and log a single warning in local environments.

#### Scenario: Production without a judge model
- **WHEN** the judge target is resolved in a production environment with `JUDGE_CHAT_MODEL` empty
- **THEN** a `ValueError` names `JUDGE_CHAT_MODEL`

### Requirement: Retry backoff is jittered and bounded
`RetryPolicy` SHALL delay retry `n` by a uniformly random fraction (injectable generator) of `min(max_delay, base * 2**(n-1))`, SHALL raise that delay to a retry-after hint capped at `max_delay`, and SHALL retry errors only when `retry_on(error)` holds (default: transient).

#### Scenario: Cap
- **WHEN** the exponential ceiling exceeds `max_delay_seconds`
- **THEN** the delay never exceeds `max_delay_seconds`

### Requirement: Rate-limit windows come from the Redis clock
`RedisRateLimiter` SHALL derive window index and elapsed time from the Redis server `TIME` inside its Lua script and SHALL NOT pass client timestamps.

#### Scenario: Two pods
- **WHEN** two limiter instances share one Redis
- **THEN** their requests count into the same window

### Requirement: Langfuse tracker typing
`LangfuseLLMTracker.client` SHALL be a `Langfuse` client or `None`; `None` means disabled (no callbacks, prompt and score calls raise, `flush` is a no-op) and a present client is flushed unconditionally.

#### Scenario: Disabled
- **WHEN** `LANGFUSE_ENABLED` is false
- **THEN** the tracker has no client and trace configs carry no callbacks
