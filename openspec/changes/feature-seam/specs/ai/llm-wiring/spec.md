## ADDED Requirements

### Requirement: LLM instance is a lifecycle resource

When `LLM_ENABLED` is true, `LlmAddon` SHALL build one `LLMInstance` with `build_llm_instance` and store it as `ApplicationResources.llm`; otherwise `resources.llm` is `None`. With no `CHAT_MODEL` the router's fake model SHALL be used, so no provider key is needed.

#### Scenario: Default settings
- **WHEN** the app starts with default settings
- **THEN** `resources.llm` is `None` and `/api/v1/completions` answers with the echo handler

#### Scenario: Enabled without a model
- **WHEN** `LLM_ENABLED=true` and `CHAT_MODEL` is empty
- **THEN** `/api/v1/completions` answers from the fake model and no network call is made

### Requirement: Streaming goes through failover

`LLMInstance.astream(...)` SHALL walk the role's chain like `ainvoke`: skip open breakers, move to the next target after a transient failure that happens before the first chunk, and report outcomes to the breaker. After the first chunk an error SHALL propagate without failover. It SHALL honour the chain deadline.

#### Scenario: Failure before first chunk
- **WHEN** the first target raises a transient error before yielding and the second target works
- **THEN** the stream yields the second target's chunks and the first target's breaker records one error

#### Scenario: Failure after first chunk
- **WHEN** a target yields one chunk and then raises
- **THEN** the error propagates and no other target is tried

### Requirement: Completions uses the LLM when present

The default completions feature SHALL use `LlmCompletionHandler(resources.llm)` when `resources.llm` is set and `EchoCompletionHandler` otherwise. `LlmCompletionHandler` SHALL implement `complete` and `stream`, filling `content`, `model`, `usage` and `finish_reason`. The worker SHALL use the same handler as the API.

#### Scenario: Same handler in API and worker
- **WHEN** `LLM_ENABLED=true` and a completion is submitted as a task
- **THEN** the task result content comes from the LLM, not from `echo:`
