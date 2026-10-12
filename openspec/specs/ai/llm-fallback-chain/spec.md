# ai/llm-fallback-chain Specification

## Purpose
The ordered model failover chain for the default role, with an independent circuit breaker per target.

## Requirements

### Requirement: The default role has an ordered failover chain
The router SHALL build the `default` chain from `CHAT_MODEL` followed by every entry of `CHAT_FALLBACK_MODELS` in order, dropping duplicates. The `judge` chain SHALL contain only the judge model.

#### Scenario: Three configured models
- **WHEN** `CHAT_MODEL=a` and `CHAT_FALLBACK_MODELS=b, c`
- **THEN** the default chain is `a, b, c`

### Requirement: Each chain target has its own breaker
With more than one target in a chain, every target SHALL sit behind its own circuit breaker counting transient failures only. A single-target chain SHALL NOT be gated.

#### Scenario: Secondary failure is tracked
- **WHEN** the second target fails transiently up to the threshold
- **THEN** its breaker opens and the chain skips it while the first target stays closed

### Requirement: ainvoke walks the chain
`LLMInstance.ainvoke` SHALL try targets in chain order, skip targets whose breaker rejects the call, report each outcome to that target's breaker, and move to the next target only after a transient failure. A deterministic error SHALL propagate immediately. When every attempted target fails transiently it SHALL raise the last error; when no target is admitted it SHALL raise `ServiceUnavailableError`.

#### Scenario: Primary and secondary overloaded
- **WHEN** targets `a` and `b` fail with 503 and `c` is healthy
- **THEN** the call is answered by `c` and the breakers of `a` and `b` each record one failure

#### Scenario: Bad prompt mid-chain
- **WHEN** target `b` fails with 400 after `a` failed with 503
- **THEN** the 400 propagates and `c` is not called

#### Scenario: Chain exhausted
- **WHEN** every target fails with a transient error
- **THEN** the error of the last target is raised
