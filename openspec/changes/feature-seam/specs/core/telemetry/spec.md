## MODIFIED Requirements

### Requirement: Completions emit GenAI telemetry without content

When telemetry is open, each LLM call made through `LLMInstance` (`ainvoke` or `astream`) SHALL record the histograms
`gen_ai.client.operation.duration`, `gen_ai.client.token.usage` (attribute
`gen_ai.token.type` of `input` or `output`) and, for streams,
`gen_ai.client.operation.time_to_first_chunk`, plus one span carrying
`gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.response.finish_reasons` and the
outcome. Failed calls SHALL carry `error.type`. No prompt or output content SHALL
be recorded. The existing completion log line SHALL be unchanged, and calls SHALL
behave identically when telemetry is off.

#### Scenario: Sync completion
- **WHEN** a sync LLM call succeeds with telemetry open
- **THEN** the duration and token-usage histograms carry the model and outcome attributes and no message content appears in any attribute

#### Scenario: Streamed completion
- **WHEN** a stream completes with telemetry open
- **THEN** the time-to-first-chunk histogram has one data point
