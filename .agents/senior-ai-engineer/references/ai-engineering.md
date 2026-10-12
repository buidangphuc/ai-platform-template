# AI Engineering Reference

Patterns for building LLM/RAG/eval features in this repo. All paths are real
anchors — read them before extending. This file is the "how AI is wired here"
companion to `fastapi-template-repo/references/architecture.md` ("where code
lives").

## LLM Access

Single entry point: `app/modules/ai/llm/runtime.py`.

```text
build_llm_instance(settings, instance_id=, service_name=, tags=)
  -> LLMInstance(chat_model: BaseChatModel, tracker: LangfuseLLMTracker)
```

Rules:

- Business code takes an `LLMInstance` (or a handler built from one) as a
  **constructor dependency**. It never calls `init_chat_model` or builds a
  provider client directly.
- App-lifetime LLM instances are composed in `app/bootstrap` and registered in
  `ApplicationResources`, exactly like other platform resources.
- `LLMInstance.trace_config(context)` returns the config you pass into the
  LangChain call so Langfuse captures the trace. Observability is not optional.

### Model selection and fallback — `ModelRouter` (`llm/router.py`)

- Resolves the target model per role: `"default"` and `"judge"` (judge model
  used by eval-as-judge flows). Reads `Settings.CHAT_MODEL`, `JUDGE_CHAT_MODEL`,
  `CHAT_FALLBACK_MODELS`. An empty `JUDGE_CHAT_MODEL` falls back to
  `CHAT_MODEL` with a warning locally and a `ValueError` outside
  dev/local/test — a judge silently grading with the production model is not
  an independent judge.
- Every model is built with bounded calls: `LLM_MAX_TOKENS`,
  `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` (the SDK's hidden retry budget,
  default 1 — the breaker only sees a call after the SDK gave up, so each
  extra retry delays failover).
- Failover is an **ordered chain**: the `default` role's chain is `CHAT_MODEL`
  followed by *every* `CHAT_FALLBACK_MODELS` entry, in order (duplicates
  dropped); `judge` has the judge model alone and no fallbacks. With more than
  one target, each target has its **own circuit breaker**
  (`CircuitBreaker`, `app/core/resilience.py`), keyed by (role, target). A
  breaker counts only *transient* failures: 408/429/5xx, timeouts and
  connection errors (`is_transient_error`). Deterministic errors (bad prompt,
  context length, content policy, other 4xx) never count and never fail over —
  the next model would only repeat them. After
  `LLM_BREAKER_FAILURE_THRESHOLD` consecutive transient failures a target's
  breaker opens and the chain skips it; after `LLM_BREAKER_COOLDOWN_SECONDS`
  exactly one call is let through to it as a probe (half-open): success closes
  the breaker, a transient failure reopens it for another cooldown. A
  single-target chain is never gated.
- The router is not discarded: `LLMInstance` carries it (`instance.router`)
  next to the tracker, and the model is resolved **per call**, because which
  target is healthy changes at runtime. Handlers call
  `await instance.ainvoke(messages, role=..., context=LLMTraceContext(...))`,
  which walks the chain: skip a target whose breaker is open, call it with the
  Langfuse trace config, report the outcome to *that target's* breaker, and
  move to the next target only after a transient failure. A deterministic
  error propagates at once; if every target fails the **last** error is
  raised; if every breaker is open, `ServiceUnavailableError`
  (`llm_unavailable`). Chosen over LangChain `with_fallbacks` because that
  wrapper cannot report outcomes to a breaker or skip an open target. Each
  failover hop adds up to one full call timeout, so keep chains short (2–3).
- Streaming / tool-binding callers use `instance.chat_model(role)` (raw model
  for the first admitted target, `ServiceUnavailableError` if none) and own
  failover and outcome reporting via `router.chain(role)`,
  `router.try_acquire(target)`, `router.record_success(target)` /
  `router.record_error(target, error=exc)`.
- With no model configured, the router returns `FakeListChatModel` — this is
  why tests and local runs work without provider keys. Lean on it for tests.

> **Open seam: the scaffold handler does not call a model.**
> `handlers/echo.py` never touches the `LLMInstance`, and no resource builds
> one yet, so nothing in the template exercises failover end to end. A real
> handler factory (in `bootstrap/services.py`) builds the instance with
> `build_llm_instance(...)` once and injects it; the handler then only calls
> `instance.ainvoke(...)`. Outcome reporting is no longer the handler's job.
> `application.py` still flushes Langfuse through the global `get_client()`
> rather than the tracker's own client (`tracker.flush()`).

## Evals — `app/modules/ai/evals/`

Evals are the test suite for AI behavior. `runner.py` gives you:

- `EvalCase(id, input, expected, metadata)` and `load_jsonl_cases(path)` — keep
  cases as `.jsonl` and treat them like regression fixtures.
- `Evaluator` protocol returning `EvalScore` (see `evaluators.py`).
- `evaluate_one(output=, expected=, evaluators=, timeout=)` — score one output.
- `run_eval_cases(cases, target=, evaluators=, tracker=, timeout=)` -> `EvalReport`
  with `total_cases` / `passed_scores`. Pass a tracker to push scores to Langfuse.

Two integration patterns (documented on `evaluate_one`):

- **Pattern A — inline gating.** Score the response inside the request flow; if
  `score.passed is False`, raise before returning. Use when a bad output must
  not reach the client. Cost: added latency on the request path.
- **Pattern B — async monitoring.** Capture the response payload and score it in
  a queue task handler (`app/modules/messaging/queue`), pushing scores to the
  tracker. Use for observability without blocking the response. Cost: scores are
  eventual, not enforced.

Choose A when correctness must gate the response, B when you only need to
observe quality. A prompt/model change ships with updated eval cases.

## RAG — `app/modules/ai/rag/`

Factory + bootstrap-addon pattern (`factory.py`):

- `build_embed_model` / `build_storage_context` / `build_rag_service` choose
  concrete backends from `RAG_*` settings and build `KnowledgeRetrievalService`.
- Defaults are `MockEmbedding` + in-memory storage; unwired backends raise an
  explicit `RuntimeError` telling you to extend the factory. **Extend the
  factory** to add a provider/vector store — do not wire providers ad hoc in
  business code.
- `RagAddon` is a `BootstrapAddon`: gated by `RAG_ENABLED`, opens the service
  into `resources.rag_service`, closes it on shutdown.
- The service carries a `RedactionPolicy` and a `TimeoutPolicy` — retrieval is
  bounded and redacted by construction. Preserve that when extending.

## Completions business service — `app/modules/business/completions/`

- `ports.py`: `CompletionHandler` Protocol = `complete(request)` + `stream(request)`;
  `stream` yields `CompletionStreamChunk` only (the last chunk may carry `usage`,
  `finish_reason`, `model`).
- `service.py`: `CompletionService` wraps one handler and exposes the same two
  methods. The service is stable; behavior lives in the handler. One instance per
  app lives on `ApplicationResources.completion_service`.
- `handlers/echo.py` is the scaffold handler.
- Stream contract (`app/api/v1/completions/streaming.py`): the endpoint awaits the
  first chunk before it sends headers, so guard violations and handler startup errors
  are normal JSON errors; first-token timeout is a JSON 504 `stream_timeout`. After the
  first chunk a failure is `event: error` with a safe code (no exception text), an idle
  gap past `STREAM_IDLE_TIMEOUT_SECONDS` is `stream_timeout`, and `: ping` comments go
  out every `SSE_HEARTBEAT_SECONDS`. Each completion logs one line (latency, ttft,
  usage, model; never content). A handler must not swallow `CancelledError`.

To add a real model-backed completion:

1. Implement `CompletionHandler` (e.g. `handlers/<name>.py`), taking an
   `LLMInstance` as a constructor dependency.
2. Pass a handler factory `create_app(completion_handler_factory=...)`; it runs in
   lifespan with the opened `ApplicationResources`, so it can take an `LLMInstance`,
   RAG service or stores from there (`app/bootstrap/services.py`).
3. Keep the API endpoint thin and the response contract unchanged.

Do not modify `CompletionService` to add behavior — swap the handler, or add checks
through `create_app(completion_guards_factory=...)` (input/output guards, fail-closed).

## Cross-cutting requirements for every AI call

- **Timeout:** wrap with `TimeoutPolicy` (`app/core/resilience`).
- **Resilience:** breaker/fallback via `ModelRouter` (LLM) or `CircuitBreaker`
  for other external calls.
- **Observability:** Langfuse trace via `LLMInstance.trace_config(...)`.
- **Redaction:** `RedactionPolicy` (`app/core/redaction`) before logging/tracing
  sensitive input or output. It masks emails, bearer/`sk-`/AWS keys, phone
  numbers (incl. Vietnamese), Luhn-valid card numbers, secret-named keys
  (`authorization`, `cookie`, `x-api-key`, ...) and recurses into lists.
- **Input/output guards:** pass `CompletionGuard`s to `CompletionService(handler,
  guards=...)` (`business/completions/guards.py`); raise `GuardrailViolation`
  (422, fail-closed). Output guards run on `complete()` only; streamed output is
  not guarded yet. An input violation in `stream()` raises on first iteration, which
  the API awaits before sending headers, so it is a 422 JSON error.
- **Untrusted content:** clients cannot send `system` messages (the server owns
  the system prompt). Retrieved text is untrusted: `knowledge_search` wraps each
  match in `<document id=... source="retrieved">` and says so in its tool
  description. Do the same for any other tool that returns third-party text, and
  delimit graded output in judge prompts.
- **Evals:** at least one eval case covering the new behavior.

> **Open seam: traces are NOT auto-redacted.** The Langfuse callback captures
> prompt/output content as-is; only RAG redacts by construction
> (`rag/service.py`). `RedactionPolicy.from_trace_content` is the intended
> hook, but it has zero callers and there is no `TRACE_CONTENT` setting — that
> flag was deliberately trimmed with the other advanced settings
> (`tests/unit/core/test_config.py` pins its absence). A product that traces
> sensitive data adds its own setting and applies the policy at the call site.
> The policy now also masks phone numbers, card numbers, AWS keys and strings in
> lists, so applying it at the call site covers more than before; it is still
> regex-based, so treat it as a floor, not a PII guarantee.

## Ship checklist for an AI feature

- [ ] Model accessed via `LLMInstance` / handler dependency, not the SDK directly.
- [ ] Model called via `LLMInstance.ainvoke` (reports outcomes + one-shot failover); raw `chat_model(role)` users report to the router themselves.
- [ ] Bounded timeout + fallback path defined.
- [ ] Trace config passed; sensitive data redacted.
- [ ] Eval cases added; gating (A) or monitoring (B) chosen deliberately.
- [ ] Unit tests (behavior + failure modes) and API contract test pass.
- [ ] `ruff` + `pyright` clean; full `pytest` if bootstrap/platform/API changed.
