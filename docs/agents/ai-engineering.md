# AI Engineering

Engineering discipline and the LLM/RAG/eval patterns of this repo. Companion to `docs/agents/architecture.md` (where code lives). All paths are real anchors; read them before extending.

## Operating principles

1. **Understand before you change.** Restate the problem in one sentence, map the flow, and locate the exact layer boundary before editing. Read a file before editing it.
2. **Smallest correct change.** Reuse repo patterns; add no layers, configs or generality "for later". Abstract only with two real call sites.
3. **Design when non-trivial.** Beyond a local edit, state the approach, the main rejected alternative and why, and name the trade-off (latency vs cost, simplicity vs flexibility).
4. **Make failure modes explicit.** Every external/model call has a bounded timeout, a fallback or circuit-breaker path, and a defined behavior on partial failure.
5. **Tests belong to the change.** Unit test service behavior and failure modes; integration test the API contract. Narrow check first, widen after touching bootstrap/platform/public API.
6. **Report like a reviewer wants.** Say what changed, what deliberately did not, assumptions, and what is risky or unverified.
7. **Stop and ask** on an ambiguous contract, an irreversible action (data/schema/external side effect) or a security-sensitive choice.

## Non-negotiables for AI features

- **Go through the platform, not the SDK.** Business code receives an `LLMInstance` (`app/modules/ai/llm/runtime.py`) or a model handler as a constructor dependency and never calls `init_chat_model` or builds a provider client. Model choice and fallback live in `ModelRouter`.
- **Three requirements:** observability (Langfuse trace via `LLMInstance.trace_config(...)`), resilience (timeout + breaker/fallback from `app/core/resilience`), eval story (cases + evaluators in `app/modules/ai/evals`).
- **Prompts are code, evals are tests.** A prompt or model change is a behavior change and ships with eval cases that gate or monitor it.
- **Redact before logging or tracing** with `RedactionPolicy` (`app/core/redaction`).
- RAG and completions have patterns (factory addon; Protocol ports + pipeline). Extend them.

## Workflow for an AI feature

1. Confirm the layer boundary in `docs/agents/architecture.md`.
2. Place the dependency: app-lifetime (LLM instance, RAG service: bootstrap + `ApplicationResources`) or request-scoped.
3. Implement business logic in `app/modules/business/<domain>`, taking the model/handler as a constructor dependency.
4. Wire observability, resilience and redaction at the call site.
5. Add or update eval cases; pick inline gating (Pattern A) or async monitoring (Pattern B).
6. Add the API dependency adapter; keep the endpoint thin.
7. Verify and state assumptions and risk. For AI behavior, run the relevant eval cases; tests run against `FakeListChatModel` (no provider keys) unless real calls are requested. Narrow-to-wide checks are in `docs/agents/architecture.md`.

## LLM access

Single entry point: `app/modules/ai/llm/runtime.py`.

```text
build_llm_instance(settings, instance_id=, service_name=, tags=)
  -> LLMInstance(chat_model: BaseChatModel, tracker: LangfuseLLMTracker)
```

- Business code takes an `LLMInstance` (or a handler built from one) as a **constructor dependency**.
- App-lifetime LLM instances are composed in `app/bootstrap` and registered in `ApplicationResources`, like other platform resources.
- `LLMInstance.trace_config(context)` returns the config passed into the LangChain call so Langfuse captures the trace.

### Model selection and fallback: `ModelRouter` (`llm/router.py`)

- Resolves the target model per role: `"default"` and `"judge"` (used by eval-as-judge flows). Reads `Settings.CHAT_MODEL`, `JUDGE_CHAT_MODEL`, `CHAT_FALLBACK_MODELS`. An empty `JUDGE_CHAT_MODEL` falls back to `CHAT_MODEL` with a warning locally and a `ValueError` outside dev/local/test, because a judge grading with the production model is not an independent judge.
- Every model is built with bounded calls: `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` (the SDK's hidden retry budget, default 1; the breaker only sees a call after the SDK gave up, so each extra retry delays failover).
- Failover is an **ordered chain**: the `default` role's chain is `CHAT_MODEL` followed by *every* `CHAT_FALLBACK_MODELS` entry, in order (duplicates dropped); `judge` has the judge model alone and no fallbacks. With more than one target, each target has its **own circuit breaker** (`CircuitBreaker`, `app/core/resilience.py`), keyed by (role, target). A breaker counts only *transient* failures: 408/429/5xx, timeouts and connection errors (`is_transient_error`). Deterministic errors (bad prompt, context length, content policy, other 4xx) never count and never fail over, since the next model would only repeat them. After `LLM_BREAKER_FAILURE_THRESHOLD` consecutive transient failures a target's breaker opens and the chain skips it; after `LLM_BREAKER_COOLDOWN_SECONDS` exactly one call is let through as a probe (half-open): success closes the breaker, a transient failure reopens it for another cooldown. A single-target chain is never gated.
- `LLMInstance` carries the router (`instance.router`) next to the tracker, and the model is resolved **per call**, because which target is healthy changes at runtime. Handlers call `await instance.ainvoke(messages, role=..., context=LLMTraceContext(...))`, which walks the chain: skip a target whose breaker is open, call it with the Langfuse trace config, report the outcome to *that target's* breaker, and move on only after a transient failure. A deterministic error propagates at once; if every target fails the **last** error is raised; if every breaker is open, `ServiceUnavailableError` (`llm_unavailable`). Chosen over LangChain `with_fallbacks` because that wrapper cannot report outcomes to a breaker or skip an open target.
- The walk has an **overall deadline**, `LLM_CHAIN_DEADLINE_SECONDS` (default 90, must be >= `LLM_TIMEOUT_SECONDS`): each attempt runs under what is left of it, and when it runs out the walk stops with `LLMDeadlineExceeded` (`AppError`, 504, `llm_deadline_exceeded`; transient-classified). An attempt cut short by the deadline is *our* budget, not the provider's fault, so it is **not** reported to that target's breaker. Per-request `LLM_TIMEOUT_SECONDS` stays the SDK's job. Keep chains short (2-3).
- Streaming / tool-binding callers use `instance.chat_model(role)` (raw model for the first admitted target, `ServiceUnavailableError` if none) and own failover and outcome reporting via `router.chain(role)`, `router.try_acquire(target)`, `router.record_success(target)` / `router.record_error(target, error=exc)`.
- With no model configured, the router returns `FakeListChatModel`; this is why tests and local runs work without provider keys. Lean on it for tests.

> **Open seam: the scaffold handler does not call a model.**
> `handlers/echo.py` never touches the `LLMInstance`, and no resource builds one yet, so nothing in the template exercises failover end to end. A real handler factory (in `bootstrap/services.py`) builds the instance with `build_llm_instance(...)` once and injects it; the handler then only calls `instance.ainvoke(...)`. Outcome reporting is not the handler's job. `application.py` still flushes Langfuse through the global `get_client()` rather than the tracker's own client (`tracker.flush()`).

## Evals: `app/modules/ai/evals/`

Evals are the test suite for AI behavior. `runner.py` provides:

- `EvalCase(id, input, expected, metadata)` and `load_jsonl_cases(path)`: keep cases as `.jsonl` regression fixtures.
- `Evaluator` protocol returning `EvalScore` (see `evaluators.py`).
- `evaluate_one(output=, expected=, evaluators=, timeout=)`: score one output.
- `run_eval_cases(cases, target=, evaluators=, tracker=, timeout=)` -> `EvalReport` with `total_cases` / `passed_scores`. Pass a tracker to push scores to Langfuse.

Two integration patterns (documented on `evaluate_one`):

- **Pattern A, inline gating.** Score the response inside the request flow; if `score.passed is False`, raise before returning. Use when a bad output must not reach the client. Cost: added latency on the request path.
- **Pattern B, async monitoring.** Capture the response payload and score it in a queue task handler (`app/modules/messaging/queue`), pushing scores to the tracker. Use for observability without blocking the response. Cost: scores are eventual, not enforced.

Choose A when correctness must gate the response, B when you only observe quality. A prompt/model change ships with updated eval cases.

## RAG: `app/modules/ai/rag/`

Factory + bootstrap-addon pattern (`factory.py`):

- `build_embed_model` / `build_storage_context` / `build_rag_service` choose concrete backends from `RAG_*` settings and build `KnowledgeRetrievalService`.
- Defaults are `MockEmbedding` + in-memory storage; unwired backends raise an explicit `RuntimeError` telling you to extend the factory. **Extend the factory** to add a provider/vector store; never wire providers ad hoc in business code.
- `RagAddon` is a `BootstrapAddon`: gated by `RAG_ENABLED`, opens the service into `resources.rag_service`, closes it on shutdown.
- The service carries a `RedactionPolicy` and a `TimeoutPolicy`, so retrieval is bounded and redacted by construction. Preserve that when extending.

## Completions business service: `app/modules/business/completions/`

The API/view shape is in `docs/agents/architecture.md` ("Canonical Feature: completions").

- `ports.py`: `CompletionHandler` Protocol = `complete(request)` + `stream(request)`; `stream` yields `CompletionStreamChunk` only (the last chunk may carry `usage`, `finish_reason`, `model`).
- `service.py`: `CompletionService(handler, *, guards, sink, policy)` wraps one handler and exposes the same two methods. Behavior lives in the handler. One instance per app lives on `ApplicationResources.completion_service`; the API and the worker share it.
- Observation: each `complete()`/`stream()` call records one `CompletionObservation` (mode, outcome `ok|error|timeout|disconnected`, duration, ttft for streams, model, finish reason, tokens; never content) to the `CompletionSink`. Bootstrap composes `FanOutSink([LogCompletionSink(), otel?])`, so every completion logs one `completion mode=...` line.
- Stream deadlines: `StreamPolicy(first_token_timeout, idle_timeout)` comes from `STREAM_FIRST_TOKEN_TIMEOUT_SECONDS` / `STREAM_IDLE_TIMEOUT_SECONDS`; a missed deadline raises `StreamTimeoutError` (504, `stream_timeout`).
- `handlers/echo.py` is the scaffold handler.
- Stream contract (`app/api/sse.py` `event_stream_response` + `CompletionService.stream`): the first event is awaited before headers, so guard violations, handler startup errors and the first-token timeout are normal JSON errors (422 / 500 / 504). After the first event a failure is `event: error` with a safe code (no exception text), an idle gap past the policy is `stream_timeout`, and `: ping` comments go out every `SSE_HEARTBEAT_SECONDS`. A handler must not swallow `CancelledError`.

To add a real model-backed completion:

1. Implement `CompletionHandler` (e.g. `handlers/<name>.py`), taking an `LLMInstance` as a constructor dependency.
2. Pass a handler factory `create_app(completion_handler_factory=...)`; it runs in lifespan with the opened `ApplicationResources`, so it can take an `LLMInstance`, RAG service or stores from there (`app/bootstrap/services.py`).
3. Keep the API endpoint thin and the response contract unchanged.

Swap the handler, or add checks through `create_app(completion_guards_factory=...)` (input/output guards, fail-closed); leave `CompletionService` unmodified.

## Cross-cutting requirements for every AI call

- **Timeout:** wrap with `TimeoutPolicy` (`app/core/resilience`).
- **Resilience:** breaker/fallback via `ModelRouter` (LLM) or `CircuitBreaker` for other external calls.
- **Observability:** Langfuse trace via `LLMInstance.trace_config(...)`.
- **Redaction:** `RedactionPolicy` (`app/core/redaction`) before logging/tracing sensitive input or output. It masks emails, bearer/`sk-`/AWS keys, phone numbers (incl. Vietnamese), Luhn-valid card numbers, secret-named keys (`authorization`, `cookie`, `x-api-key`, ...) and recurses into lists.
- **Input/output guards:** pass `CompletionGuard`s to `CompletionService(handler, guards=...)` (`business/completions/guards.py`); raise `GuardrailViolation` (422, fail-closed). Output guards run on `complete()` only; streamed output is not guarded yet. An input violation in `stream()` raises on first iteration, which the API awaits before sending headers, so it is a 422 JSON error.
- **Untrusted content:** clients cannot send `system` messages (the server owns the system prompt). Retrieved text is untrusted: `knowledge_search` wraps each match in `<document id=... source="retrieved">` and says so in its tool description. Do the same for any tool that returns third-party text, and delimit graded output in judge prompts.
- **Evals:** at least one eval case covering the new behavior.

> **Open seam: traces are NOT auto-redacted.**
> The Langfuse callback captures prompt/output content as-is; only RAG redacts by construction (`rag/service.py`). `RedactionPolicy.from_trace_content` is the intended hook, but it has zero callers and there is no `TRACE_CONTENT` setting; that flag was deliberately trimmed with the other advanced settings (`tests/unit/core/test_config.py` pins its absence). A product that traces sensitive data adds its own setting and applies the policy at the call site. The policy is regex-based: a floor, not a PII guarantee.

## Ship checklist for an AI feature

- [ ] Model accessed via `LLMInstance` / handler dependency, not the SDK directly.
- [ ] Model called via `LLMInstance.ainvoke` (reports outcomes + failover); raw `chat_model(role)` users report to the router themselves.
- [ ] Bounded timeout + fallback path defined.
- [ ] Trace config passed; sensitive data redacted.
- [ ] Eval cases added; gating (A) or monitoring (B) chosen deliberately.
- [ ] Unit tests (behavior + failure modes) and API contract test pass.
- [ ] `ruff` + `pyright` clean; full `pytest` if bootstrap/platform/API changed.
