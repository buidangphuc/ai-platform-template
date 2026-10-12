# ai/llm-chain-deadline Specification

## Purpose
An overall deadline for walking the model failover chain, so a request never waits on every target's timeout.

## Requirements

### Requirement: The chain walk has an overall deadline
`LLM_CHAIN_DEADLINE_SECONDS` SHALL bound one `LLMInstance.ainvoke` call across every target it tries, and SHALL be validated to be greater than or equal to `LLM_TIMEOUT_SECONDS`. Each attempt SHALL run under the time remaining. When the deadline passes, in an attempt or between targets, `ainvoke` SHALL stop walking and raise `LLMDeadlineExceeded` (status 504, code `llm_deadline_exceeded`), which `is_transient_error` classifies as transient.

#### Scenario: Slow chain is cut at the deadline
- **WHEN** the deadline is 3s and the first two targets each take 3s
- **THEN** the call fails with `LLMDeadlineExceeded` at about 3s and later targets are not called

#### Scenario: Deadline below the call timeout
- **WHEN** `LLM_CHAIN_DEADLINE_SECONDS` is lower than `LLM_TIMEOUT_SECONDS`
- **THEN** settings validation fails

### Requirement: A deadline cut is not a breaker failure
An attempt cancelled because the chain deadline expired SHALL NOT be reported to that target's circuit breaker.

#### Scenario: Slow target cut by the deadline
- **WHEN** a target is still running when the deadline expires
- **THEN** its breaker failure count is unchanged
