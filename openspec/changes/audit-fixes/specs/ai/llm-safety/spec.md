## ADDED Requirements

### Requirement: No fake model outside local environments

`Settings` SHALL reject `LLM_ENABLED=true` with an empty `CHAT_MODEL` unless `ENVIRONMENT` is local. In a local environment the fake model SHALL still be served and a warning logged once.

#### Scenario: Production without a model
- **WHEN** `ENVIRONMENT` is production, `LLM_ENABLED` is true and `CHAT_MODEL` is empty
- **THEN** settings validation fails naming `CHAT_MODEL`

#### Scenario: Local without a model
- **WHEN** `ENVIRONMENT` is local with the same flags
- **THEN** the app starts and completions return the fake response

### Requirement: The chain deadline leaves room for failover

`Settings` SHALL require `LLM_CHAIN_DEADLINE_SECONDS >= LLM_TIMEOUT_SECONDS * (LLM_MAX_RETRIES + 1)`. The default `LLM_TIMEOUT_SECONDS` SHALL be 30 so the defaults satisfy the rule and leave time for a fallback target.

#### Scenario: Budget too small
- **WHEN** timeout is 60, retries 1 and deadline 90
- **THEN** settings validation fails naming the three settings

#### Scenario: Hung primary reaches the fallback
- **WHEN** the primary target times out on every attempt and a fallback target is configured, with default settings
- **THEN** `ainvoke` returns the fallback's answer and the primary's breaker records a failure

### Requirement: A first-token stall fails over

When a stream yields no chunk within the first-token timeout, `astream` SHALL record a breaker failure for that target and try the next target of the chain while the chain deadline allows; with no target left it SHALL raise `StreamTimeoutError` as before. After the first chunk, behaviour is unchanged.

#### Scenario: Stall then fallback
- **WHEN** the primary yields nothing within the first-token timeout and a fallback exists
- **THEN** the stream continues from the fallback and one failure is recorded for the primary

#### Scenario: Stall with no fallback
- **WHEN** there is a single target and it stalls
- **THEN** `StreamTimeoutError` is raised and the outcome label is `timeout`

### Requirement: Traces are flushed in every process

The LLM addon SHALL flush Langfuse when its exit stack unwinds, in the API and in the worker. The API lifespan SHALL NOT have its own flush.

#### Scenario: Worker shutdown
- **WHEN** `worker_context` exits with `LLM_ENABLED` and `LANGFUSE_ENABLED`
- **THEN** the tracker's flush is called once

#### Scenario: Langfuse disabled
- **WHEN** `LANGFUSE_ENABLED` is false
- **THEN** no flush is attempted

### Requirement: The eval gate grades the configured handler

`scripts/run_eval.py` SHALL build the completion service through the same runtime as the app (`open_runtime` with the default features) so that `LLM_ENABLED=true` grades the model-backed handler. With `LLM_ENABLED=false` it grades the echo handler and stays hermetic.

#### Scenario: Hermetic default
- **WHEN** the gate runs with `.env.example`
- **THEN** output and exit code are the same as before this change

#### Scenario: Model-backed
- **WHEN** the gate runs with `LLM_ENABLED=true` and a model builder that returns a fake chat model
- **THEN** the graded output comes from that model, not from the echo handler
