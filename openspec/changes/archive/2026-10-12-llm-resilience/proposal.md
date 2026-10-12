## Why

The audit of the LLM runtime and resilience primitives found that failover could never engage and that the primitives encoded the wrong semantics:

- The primary breaker counted 4xx (deterministic failures such as a bad prompt or context overflow) and ignored timeouts and connection errors, so it tripped on the wrong errors and stayed closed through real outages. Once open it never recovered: there was no cooldown or probe.
- `build_chat_model` built a `ModelRouter`, called `.chat_model()` once and threw the router away; `LLMInstance` held a single fixed model, so no caller could fail over or report outcomes.
- Models were built without `max_tokens`, `timeout` or `max_retries`; provider SDK defaults (long timeouts, hidden retries) applied.
- The judge model silently fell back to the production model.
- The Redis rate limiter keyed windows on each pod's `time.monotonic`, so pods disagreed on window boundaries.
- `RetryPolicy` waited 0s before the first retry, had no jitter, retried every exception and ignored `Retry-After`.
- `LangfuseLLMTracker` used `Any`, an `enabled` flag next to a lazily built env-configured client, and `hasattr` checks.

## What Changes

- One definition of a transient failure (`is_transient_error`): 408, 429, 5xx, timeouts, connection errors. The breaker counts only these; deterministic 4xx never trips failover.
- `CircuitBreaker` is closed / open / half-open with a cooldown and a single probe; `record_failure(error)` replaces `record_failure(status_code=)`; `allows_request` / `is_open` / policy status fields are removed. **BREAKING** for direct users of the breaker and `ModelRouter.record_error(status_code=)` (now `error=`; `current_target` is now `select_target`).
- `LLMInstance` carries the `ModelRouter` and resolves the model per call. `LLMInstance.ainvoke` selects the target, attaches the trace config, reports the outcome and retries once on the secondary after a transient primary failure. **BREAKING**: `LLMInstance.chat_model` is now a method (raw model for streaming); `build_chat_model` is removed.
- New settings `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` (default 1), `LLM_BREAKER_FAILURE_THRESHOLD`, `LLM_BREAKER_COOLDOWN_SECONDS`, passed to `init_chat_model`.
- The judge role raises in non-local environments (warns once locally) when `JUDGE_CHAT_MODEL` is empty but `CHAT_MODEL` is set.
- `RedisRateLimiter` computes window index and elapsed time from `redis.call('TIME')` inside the Lua script; its `clock` parameter is removed. The in-memory limiter keeps its monotonic clock.
- `RetryPolicy` uses capped exponential backoff with full jitter (injectable `rng`), a `retry_on` predicate defaulting to `is_transient_error`, and honors a retry-after hint. `backoff_seconds` is replaced by `base_delay_seconds` / `max_delay_seconds`. The outbox publisher keeps retrying every sink error through an explicit `retry_on`.
- `LangfuseLLMTracker.client` is `Langfuse | None` (None = disabled), built from settings; the `enabled` flag, lazy env client and `hasattr` check are gone.

## Capabilities

### New Capabilities
- `ai/llm`: failure classification, circuit breaker, per-call model resolution with failover, bounded provider calls, judge separation, tracker typing.

### Modified Capabilities
None.

## Impact

- Code: `app/modules/ai/llm/**`, `app/core/resilience.py`, `app/modules/platform/rate_limit/service.py`, `app/core/config/ai.py`, `.env.example`, `app/modules/messaging/{outbox/publisher,webhooks/dispatcher}.py`, smoke scripts; tests under `tests/unit/`.
- Docs: `.agents/senior-ai-engineer/references/ai-engineering.md` (model selection and open seam), `app/core/README.md`.

## Follow-ups

- `app/bootstrap/application.py` flushes Langfuse via the global `get_client()`; it should flush the owned tracker (`tracker.flush()`).
- No bootstrap resource builds an `LLMInstance` yet; the first real handler factory does.
- The secondary target has no breaker, and only the first `CHAT_FALLBACK_MODELS` entry is used.
- The Redis limiter's script-built window keys are not Cluster-safe.
