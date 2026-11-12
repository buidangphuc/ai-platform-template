Execution: one wave of five packets, each written by a Sonnet subagent in its own worktree, branched from `chore/audit-cleanup`. Packets own disjoint files; a packet touches nothing outside its `Owns:` list. Each packet writes its named tests first and sees them fail (or, where marked "characterization", sees them pass before touching the code), runs the checks in `docs/agents/project.md` "Checks" (the CI list, without infra), and makes one commit. The orchestrator reviews, cherry-picks and runs `make test-infra` once after the wave.

## 1. Webhook retries and retry policy

Owns: `app/modules/messaging/webhooks/dispatcher.py`, `app/modules/messaging/webhooks/factory.py` (delete), `app/modules/messaging/outbox/publisher.py`, `app/bootstrap/addons/webhooks.py`, `app/core/resilience.py`, `app/core/config/messaging.py`, `.env.example`, `tests/unit/modules/test_webhooks.py`, `tests/unit/modules/test_outbox.py`, `tests/unit/core/test_resilience.py`.
Contract:
- `HttpWebhookDispatcher(*, signer, client, timeout_policy=None, retry_policy=DEFAULT_WEBHOOK_RETRY_POLICY, sleep=asyncio.sleep)`.
- `async send_once(url, envelope) -> WebhookDeliveryResult`: today's body of `dispatch`, one signed request.
- `async dispatch(url, envelope) -> WebhookDeliveryResult`: loop over `send_once`; after attempt N ask `retry_policy.decision(attempt=N, status_code=...)` for a status result or `decision(attempt=N, error=...)` for a transport error or timeout; when `should_retry`, `await sleep(delay)` and try again; return the last result. A numeric `Retry-After` response header is passed as `retry_after_seconds`.
- `DEFAULT_WEBHOOK_RETRY_POLICY` retries refused connections and timeouts (set `retry_on` if `is_transient_error` does not cover the httpx error).
- `WEBHOOK_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=10)` next to the other `WEBHOOK_*` settings and in `.env.example`; `WebhookAddon` builds the dispatcher with `dataclasses.replace(DEFAULT_WEBHOOK_RETRY_POLICY, max_attempts=settings.WEBHOOK_MAX_ATTEMPTS)`.
- `RetryPolicy` loses the field `retry_exceptions`; `decision` uses `retry_on(error)` alone and calls `retry_after_seconds(error)` directly (rename the `decision` parameter's local use so `_error_retry_after` is not needed). `CircuitBreaker.reset` is deleted.

- [x] 1.1 Write `test_dispatch_retries_transient_status_then_succeeds`, `test_dispatch_does_not_retry_non_retryable_status`, `test_dispatch_stops_after_max_attempts`, `test_dispatch_retries_refused_connection_and_timeout`, `test_dispatch_honours_numeric_retry_after`, `test_each_attempt_is_signed_with_its_own_timestamp`, `test_send_once_makes_one_request` in `test_webhooks.py` with an injected `sleep` that records delays; verify red
- [x] 1.2 Implement `send_once`, the retry loop and the `sleep` parameter; verify 1.1 green and that no test sleeps for real
- [x] 1.3 `WebhookOutboxSink.publish` calls `send_once`; write `test_webhook_outbox_sink_sends_once_per_publish` in `test_outbox.py`; verify red then green
- [x] 1.4 Add `WEBHOOK_MAX_ATTEMPTS` (settings, `.env.example`, addon); write `test_webhook_addon_uses_max_attempts_setting`; verify it and `python -m scripts.check_env_example`
- [x] 1.5 Remove `retry_exceptions`, `_error_retry_after`, `CircuitBreaker.reset`; replace the `retry_exceptions=False` test in `test_resilience.py` with one that passes `retry_on=lambda error: False`; delete `webhooks/factory.py`; verify `rg "retry_exceptions|_error_retry_after|webhooks.factory" app tests scripts` is empty

## 2. Settings summary, worker entry and small deletions

Owns: `app/core/config/__init__.py`, `app/bootstrap/application.py`, `app/bootstrap/worker.py`, `scripts/run_worker.py`, `app/modules/messaging/tasks/store.py`, `app/modules/platform/rate_limit/factory.py` (delete), `app/bootstrap/addons/rate_limit.py`, `app/modules/platform/mongo/factory.py`, `tests/unit/core/test_config.py`, `tests/unit/core/test_application_lifespan.py`, `tests/unit/test_run_worker_entry.py`, `tests/unit/modules/test_rate_limit.py`.
Contract: `Settings.redacted_summary()` as in `specs/core/settings-summary/spec.md`. Log call: `logger.info("settings {}", settings.redacted_summary())`, in the API lifespan start when `init_resources` is true and in `scripts/run_worker.py::_run` before `worker_context`. `worker_context(settings=None, *, features=FEATURES)`; `WorkerContext` has no `settings` field.

- [x] 2.1 Write `test_redacted_summary_masks_secret_words`, `test_redacted_summary_masks_url_credentials` (`MONGODB_URI`, `RABBITMQ_URL`, `POSTGRES_URL`), `test_redacted_summary_keeps_non_secret_values` (`LLM_MAX_TOKENS`, `IDEMPOTENCY_KEY_MAX_LENGTH`, `STREAM_FIRST_TOKEN_TIMEOUT_SECONDS`, credential-free `MONGODB_URI`), `test_redacted_summary_keeps_empty_secret_empty` in `test_config.py`, replacing the two existing `redacted_summary` tests; verify red
- [x] 2.2 Rewrite the masking rule; verify 2.1 green
- [x] 2.3 Write `test_lifespan_logs_redacted_settings_once`, `test_lifespan_without_resources_does_not_log_settings` in `test_application_lifespan.py` and `test_worker_entry_logs_redacted_settings` in `test_run_worker_entry.py`; verify red; add the two log calls; verify green
- [x] 2.4 Remove `--check`, `check_worker_configuration`, `WorkerContext.settings` and the `addons` parameter; replace the `--check` tests with `test_check_argument_is_rejected_as_unknown`; verify `rg "check_worker_configuration|\"--check\"" app scripts tests` shows only that test
- [x] 2.5 Remove `TaskRecord.metadata`; delete `rate_limit/factory.py` and build `RedisRateLimiter` in the addon; `test_rate_limit.py` constructs `RedisRateLimiter` directly; drop the `if TYPE_CHECKING: pass` block and its import in `mongo/factory.py`; verify `rg "build_redis_rate_limiter|rate_limit.factory" app tests` is empty and `tests/unit/modules/test_rate_limit.py` passes on infra if available (it carries the `infra` marker; say so in the report if it could not run)

## 3. One eval loop

Owns: `app/modules/ai/evals/runner.py`, `scripts/run_eval.py`, `tests/unit/modules/test_evals.py`, `tests/unit/test_run_eval_entry.py`, `docs/agents/ai-engineering.md`, `evals/README.md`.
Contract: `run_eval_cases` and `EvalReport` as in `specs/ai/eval-gate/spec.md`; `EvalCaseResult` gains `skipped: bool = False`. `scripts/run_eval.py` keeps its CLI, its JSON keys and its exit codes; the selector maps `metadata.evaluator` (`exact` default, `contains`, `judge`) to one evaluator, returns an empty sequence for `judge` without `JUDGE_CHAT_MODEL`, and unknown values are rejected before scoring. `app/modules/ai/evals/evaluators.py` is not touched.

- [x] 3.1 Record the current output of `uv run --env-file .env.example --all-extras python -m scripts.run_eval --min-score 0.8` in the report (characterization)
- [x] 3.2 Write `test_run_eval_cases_accepts_a_per_case_selector`, `test_run_eval_cases_skips_case_without_evaluators_and_does_not_call_target`, `test_eval_report_pass_rate_and_failures`, `test_eval_report_pass_rate_is_zero_without_scores` in `test_evals.py`; verify red; implement; verify green and that the existing runner tests still pass
- [x] 3.3 Write `test_eval_gate_rejects_unknown_evaluator` and `test_eval_gate_counts_skipped_judge_cases` in `test_run_eval_entry.py`; verify red
- [x] 3.4 `scripts/run_eval.py` builds the selector and calls `run_eval_cases`; verify 3.3 green, the two existing gate tests green, and the 3.1 command prints the same JSON
- [x] 3.5 Docs: `docs/agents/ai-engineering.md:79` (signature, selector, new report fields), `:102` (`CompletionService(handler, *, guards, policy)`; there is no `sink`), `evals/README.md` (unknown evaluator fails the gate)

## 4. Core deletions and validation message tests

Owns: `app/core/errors.py`, `app/core/logging.py`, `app/core/README.md`, `tests/unit/core/test_errors.py`, `tests/unit/core/test_error_envelope.py`, `tests/unit/core/test_logging.py`.
Contract: `format_validation_errors` and `PYDANTIC_ERROR_MESSAGES` are not changed. `configure_logging` loses the `noisy_loggers` parameter and always silences `_NOISY_LOGGERS`.

- [x] 4.1 Characterization tests, all passing before any code change: `test_422_missing_field_uses_template_message`, `test_422_formats_message_from_ctx` (HTTP, in `test_error_envelope.py`), `test_format_validation_errors_keeps_unknown_type_message`, `test_format_validation_errors_uses_unformatted_template_when_ctx_is_missing` (in `test_errors.py`). A failure here is a finding: report it, do not change `errors.py` to make it pass
- [x] 4.2 Delete `ServerError` and `TokenError` and their rows in `test_errors.py`; verify `rg "\bServerError\b|\bTokenError\b" app tests scripts` shows only `ServerErrorMiddleware` mentions
- [x] 4.3 Delete `log = logger` and the `noisy_loggers` parameter; the logging test calls `configure_logging()` and asserts the default noisy loggers are silenced; verify `tests/unit/core/test_logging.py`
- [x] 4.4 `app/core/README.md`: errors table without `ServerError` / `TokenError`; `RetryPolicy` field list without `retry_exceptions`; layout trees add `aws_errors.py`, `telemetry.py`, `telemetry_otel.py`, `config/conversations.py`, `config/telemetry.py`; resilience "Used by" adds `platform/http/upstream.py`; pagination is used by `app/api/v1/conversations/router.py` (drop "Not yet wired"); `redacted_summary` is logged at start

## 5. Repo config and docs

Owns: `pyproject.toml`, `uv.lock`, `.gitignore`, `.dockerignore`, `.pre-commit-config.yaml`, `alembic/README` (delete), `openspec/changes/archive/**` (delete), `Makefile`, `README.md`, `docs/usage.md`, `docs/template-guide.md`.

- [x] 5.1 Remove `openai` from the `ai` extra; `uv lock`; verify `uv lock --check`, `openai` still resolved in `uv.lock` through `langchain-openai`, and `uv run --all-extras python -c "import openai, langchain_openai"`
- [x] 5.2 `git rm -r openspec/changes/archive`; delete `alembic/README`; verify `uv run alembic history` still lists 10 revisions and `openspec validate audit-cleanup --strict`
- [x] 5.3 `.gitignore`: drop `.mypy_cache/`, `.python-version`, `.local/`, `logs/`, `data/`; add `.codegraph/`. `.dockerignore`: drop `.mypy_cache/`, `logs/`, `data/`, `!README.md`; add `.uv-cache/`, `.codegraph/`, `openspec/`. `.pre-commit-config.yaml`: drop the `ci:` block and the `check-json` hook. Verify `SKIP=commitizen uv run pre-commit run --all-files --hook-stage pre-commit` and `git status --short` shows no newly untracked file
- [x] 5.4 `Makefile`: add `worker`, `test-fast`, `check-env` to `.PHONY`
- [x] 5.5 Docs, each checked against the code it describes:
  - `docs/usage.md:7` Python `>=3.12,<3.14`
  - `docs/usage.md:73` and `docs/template-guide.md:35-40`: `ops/compose/local.yaml` already runs api + worker + postgres + redis with queue, tasks and outbox on
  - `docs/usage.md:114` and `docs/template-guide.md:190`: `make test` runs `pytest -m "not infra"`; `make test-infra` runs everything on localinfra
  - `docs/usage.md:265-267`: object storage (`platform/objects`), queues (`messaging/queue`) and OpenTelemetry (`core/telemetry_otel.py`) are wrapped; keep only what is truly not wrapped
  - `docs/template-guide.md:52-53`: `router.py` holds the endpoints and declares its own prefix and `Depends(require_principal)`; a second file exists only for `task_routers`
  - `docs/template-guide.md:101-106`: `ai` row without `openai`; add the `otel` row from `pyproject.toml`
  - `README.md:21`: no connection is opened and no optional package is needed, but `POSTGRES_*` and `REDIS_HOST` must be set (the values in `.env.example` are enough)
  - Verify `tests/integration/test_docs.py` and `rg -n "full pytest" docs README.md` is empty
