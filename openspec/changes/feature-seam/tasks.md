Execution: packets run one at a time on branch `feat/feature-registry` in the shared checkout (no worktrees; packets share `resources.py` and `services.py`). Each packet's subagent writes tests first and sees them fail, runs the repo's full checks, and does not commit; the orchestrator reviews and commits.

## 1. Feature registry

Owns: `app/bootstrap/features/{__init__,base,completions,registry}.py`, `app/bootstrap/{resources,services,application,worker}.py`, `app/api/router.py`, `app/api/v1/completions/{router,tasks}.py`, `alembic/env.py`, `app/modules/messaging/queue/worker.py`, `scripts/run_eval.py`, `tests/**` touching `completion_handler_factory`, `completion_guards_factory`, `completion_service`, `TypedMessageDispatcher`, new `tests/unit/core/test_features.py`, `docs/agents/architecture.md`, `docs/template-guide.md`, `docs/usage.md`.
Contract: `Feature` fields as in `specs/core/feature-registry/spec.md`; `resources.service(cls)`; `create_app(features=FEATURES)`, `worker_context(features=FEATURES)`; `completions_feature(handler_factory=default, guards_factory=default)`.

- [ ] 1.1 Write `test_features.py` (second fake feature: route, service, task handler, disabled, duplicate type, unknown type); verify red then green
- [ ] 1.2 Add `Feature`, `registry`, `completions_feature`; replace `completion_service` with `resources.service(cls)`; verify `test_features.py`
- [ ] 1.3 `create_app`, `worker_context`, `build_api_router` take `features`; worker dispatches by `task.type`; delete `TypedMessageDispatcher` and its tests; verify worker tests
- [ ] 1.4 `alembic/env.py` imports feature models; verify `test_feature_models_in_metadata`
- [ ] 1.5 Port the 7 tests that pass factories; update docs; verify full pytest, `rg "completion_handler_factory=|completion_service\b" app scripts` empty except `features/completions.py`

## 2. LLM wired

Owns: `app/core/config/ai.py`, `.env.example`, `app/bootstrap/addons/{llm,base}.py`, `app/bootstrap/resources.py` (field `llm` only), `app/modules/ai/llm/runtime.py`, `app/modules/business/completions/handlers/llm.py`, `app/bootstrap/features/completions.py`, `scripts/run_eval.py`, `docs/agents/ai-engineering.md`, tests under `tests/unit/modules/test_llm_runtime.py`, `tests/unit/modules/completions/`, `tests/integration/`.
Contract: `LLMInstance.astream(input, *, role="default", context=None) -> AsyncIterator[BaseMessageChunk]`.

- [ ] 2.1 `LLM_ENABLED` setting + `.env.example`; verify `check-env`
- [ ] 2.2 `LlmAddon` + `resources.llm`; verify `test_llm_addon_*`
- [ ] 2.3 `LLMInstance.astream` with failover before first chunk; verify `test_astream_fails_over_before_first_chunk`, `test_astream_no_failover_after_first_chunk`
- [ ] 2.4 `LlmCompletionHandler`; `completions_feature` picks it when `resources.llm`; verify integration sync, stream and task return model content

## 3. Observation in LLMInstance

Owns: `app/core/telemetry.py`, `app/core/telemetry_otel.py`, `app/bootstrap/addons/{llm,telemetry}.py`, `app/modules/ai/llm/runtime.py`, `app/modules/business/completions/service.py`, `app/bootstrap/features/completions.py`, related tests, `docs/usage.md`, `docs/agents/ai-engineering.md`.
Contract: `LlmObservation` keeps the fields of `CompletionObservation`; `LlmSink.record_llm(observation)`; the log line format is unchanged.

- [ ] 3.1 Rename the sink types; `LLMInstance` takes `sink` and records one observation per `ainvoke`/`astream`; verify `test_llm_observation_*`
- [ ] 3.2 `astream` takes first-token and idle timeouts and records `timeout` and `disconnected`; verify the disconnect and timeout tests
- [ ] 3.3 `CompletionService` drops sink and `_Observation`, keeps guards and `StreamPolicy`; verify `test_completion_telemetry.py` with `LLM_ENABLED=true`

## 4. Upstream HTTP

Owns: `app/modules/platform/http/{__init__,upstream}.py`, `app/bootstrap/features/base.py` (field `upstreams` only), `app/bootstrap/resources.py`, `app/modules/platform/model_server/client.py`, `docs/template-guide.md` section 5, `tests/unit/modules/test_upstream.py`.

- [ ] 4.1 `Upstream` + `UpstreamClient` over `httpx.MockTransport`-testable client with `RetryPolicy`, `CircuitBreaker`, `TimeoutPolicy`; verify retry, breaker, isolation, request-id tests
- [ ] 4.2 Bootstrap opens upstreams for enabled features and closes them; `resources.http(name)`; verify duplicate and unknown name tests
- [ ] 4.3 `ModelServerClient` takes `UpstreamClient`; delete `build_httpx_model_server_client`; verify model-server tests

## 5. One DB pattern and the conversations sample

Owns: `app/core/database/engine.py`, `app/modules/platform/mongo/dependency.py`, `app/bootstrap/state.py`, `app/modules/business/conversations/**`, `app/api/v1/conversations/**`, `app/bootstrap/features/{conversations,registry}.py`, `app/core/config/{conversations,__init__}.py`, `.env.example`, `alembic/versions/0010_create_conversations.py`, `app/core/README.md`, `docs/usage.md`, `docs/template-guide.md`, related tests.

- [ ] 5.1 Remove `DbSession`, `get_db`, `MongoDep`, `get_mongo`, `get_mongo_gateway` and their tests; verify `rg` empty
- [ ] 5.2 Settings + validator for `CONVERSATIONS_ENABLED`; verify config tests
- [ ] 5.3 Models, migration 0010, store, service; verify aiosqlite unit tests (history order, transaction rollback on LLM failure, principal scoping)
- [ ] 5.4 Router (create, list with `PaginationParams`, messages, send) + feature; verify integration tests; run `alembic upgrade head` then `downgrade -1` on local Postgres if available

## 6. Optional route guards

Owns: `app/modules/platform/quota/http.py`, `app/modules/platform/idempotency/http.py`, `docs/usage.md`, `tests/integration/test_route_guards.py`.

- [ ] 6.1 `require_quota`; verify 429 and no-handler-run test
- [ ] 6.2 `@idempotent`; verify replay and no-header tests
- [ ] 6.3 Docs say opt-in and show one example; verify `rg "require_quota|idempotent" app/api` empty
