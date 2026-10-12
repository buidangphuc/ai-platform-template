# api/completions-safety Specification

## Purpose
The request contract, result contract and guardrail seam of the completions API.

## Requirements

### Requirement: Clients cannot supply system messages

The completions API SHALL accept only `user` and `assistant` message roles from clients. The
system prompt SHALL be owned by the server.

#### Scenario: System role rejected
- **WHEN** a client posts a message with role `system`
- **THEN** the response is 422 with code `validation_error`

### Requirement: Completion requests are bounded and strict

A completion request SHALL contain at most 64 messages, each at most 32,000 characters, and metadata
of at most 32 keys and 4,096 serialized bytes. Unknown fields SHALL be rejected.

#### Scenario: Oversized content rejected
- **WHEN** a message exceeds 32,000 characters
- **THEN** the response is 422

#### Scenario: Unknown field rejected
- **WHEN** the body contains a field the contract does not define
- **THEN** the response is 422

### Requirement: Completion results report usage and finish reason

A completion result and response SHALL carry optional `usage` (input, output and total tokens) and
`finish_reason`.

#### Scenario: Echo handler reports usage
- **WHEN** `POST /api/v1/completions` is served by the scaffold echo handler
- **THEN** the response contains `finish_reason` `stop` and a `usage` object with non-negative token counts

### Requirement: Completion guardrails are fail-closed

The completion service SHALL run configured guards in order: input guards before the handler,
output guards on the handler's result. A guard raising `GuardrailViolation` SHALL produce a 422 with
code `guardrail_input_violation` or `guardrail_output_violation`. Any other guard failure SHALL abort
the request. Streaming SHALL run input guards before the handler streams and SHALL NOT yet run output guards.

#### Scenario: Input violation skips the handler
- **WHEN** an input guard raises `GuardrailViolation`
- **THEN** the handler is not called and the response is 422

#### Scenario: Output violation withholds the result
- **WHEN** an output guard raises `GuardrailViolation`
- **THEN** the response is 422 with code `guardrail_output_violation`

#### Scenario: Guard crash blocks the request
- **WHEN** a guard raises an unexpected exception
- **THEN** the handler's result is not returned
