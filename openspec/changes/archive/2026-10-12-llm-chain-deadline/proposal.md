## Why

`LLMInstance.ainvoke` walks the fallback chain, but each hop may consume a full `LLM_TIMEOUT_SECONDS`, so a 3-model chain can take 3x the budget with no overall deadline (the follow-up recorded in `fallback-chain-and-eager-clients`).

## What Changes

- New setting `LLM_CHAIN_DEADLINE_SECONDS` (default 90, `0 < x <= 1800`), validated `>= LLM_TIMEOUT_SECONDS`; in `.env.example`.
- `ainvoke` computes one deadline per call. Each attempt runs under `asyncio.timeout(remaining)`; when the budget is gone the walk stops and raises `LLMDeadlineExceeded`.
- `LLMDeadlineExceeded` is an `AppError` with status 504 and code `llm_deadline_exceeded`, defined in `app/modules/ai/llm/runtime.py`. Status >= 500 makes `is_transient_error` true, and the standard error envelope renders it. No new core error class was added.
- An attempt cut short by the deadline is not reported to the target's breaker: it is our budget, not the provider's failure.
- The per-request `LLM_TIMEOUT_SECONDS` is deliberately not re-applied as `min(remaining, timeout)`: the SDK already enforces it per request, and re-applying it would cancel the SDK's own `LLM_MAX_RETRIES` budget.

## Capabilities

### New Capabilities
- `ai/llm-chain-deadline`: overall deadline across the fallback chain.

### Modified Capabilities
None.

## Impact

- Code: `app/modules/ai/llm/runtime.py`, `app/core/config/ai.py`, `.env.example`; tests `tests/unit/modules/test_llm_runtime.py`, `tests/unit/core/test_config.py`.
- Docs: `.agents/senior-ai-engineer/references/ai-engineering.md` (model selection).
- **Behaviour change**: calls slower than the deadline now fail with 504 instead of running on. Raise `LLM_CHAIN_DEADLINE_SECONDS` if a deployment sets `LLM_TIMEOUT_SECONDS` above 90 (startup validation rejects a deadline below the timeout).

## Follow-ups

- A breaker probe slot taken by an attempt that the deadline then cancels is re-granted only after one more cooldown (existing "unreported probe" behaviour); `CircuitBreaker` has no public release.
