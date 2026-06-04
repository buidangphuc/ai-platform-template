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
  `CHAT_FALLBACK_MODELS`.
- Primary → secondary fallback is driven by a **circuit breaker on 4xx**
  (`CircuitBreakerPolicy`, `failure_status_range=range(400, 500)`). After each
  call the caller must report the outcome:
  - `record_success(target, role=...)`
  - `record_error(target, status_code=..., role=...)`
  When the primary breaker opens, `current_target` returns the secondary.
- With no model configured, `chat_model()` returns `FakeListChatModel` — this is
  why tests and local runs work without provider keys. Lean on it for tests.

When adding a model call: get the target from the router, invoke with the
trace config, then record success/error so fallback health stays accurate.

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

## Completions business pipeline — `app/modules/business/completions/`

- `ports.py`: `CompletionHandler` Protocol = `complete(request)` + `stream(request)`.
- `pipeline.py`: `CompletionPipeline` wraps one handler and exposes the same two
  methods. The pipeline is stable; behavior lives in the handler.
- `handlers/echo.py` is the scaffold handler.

To add a real model-backed completion:

1. Implement `CompletionHandler` (e.g. `handlers/<name>.py`), taking an
   `LLMInstance` as a constructor dependency.
2. Compose it in bootstrap and inject it into `CompletionPipeline`.
3. Keep the API endpoint thin and the response contract unchanged.

Do not modify `CompletionPipeline` to add behavior — swap the handler.

## Cross-cutting requirements for every AI call

- **Timeout:** wrap with `TimeoutPolicy` (`app/core/resilience`).
- **Resilience:** breaker/fallback via `ModelRouter` (LLM) or `CircuitBreaker`
  for other external calls.
- **Observability:** Langfuse trace via `LLMInstance.trace_config(...)`.
- **Redaction:** `RedactionPolicy` (`app/core/redaction`) before logging/tracing
  sensitive input or output.
- **Evals:** at least one eval case covering the new behavior.

## Ship checklist for an AI feature

- [ ] Model accessed via `LLMInstance` / handler dependency, not the SDK directly.
- [ ] Outcome reported to `ModelRouter` (`record_success` / `record_error`).
- [ ] Bounded timeout + fallback path defined.
- [ ] Trace config passed; sensitive data redacted.
- [ ] Eval cases added; gating (A) or monitoring (B) chosen deliberately.
- [ ] Unit tests (behavior + failure modes) and API contract test pass.
- [ ] `ruff` + `pyright` clean; full `pytest` if bootstrap/platform/API changed.
