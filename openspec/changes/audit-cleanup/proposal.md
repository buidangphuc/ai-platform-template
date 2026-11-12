## Why

A whole-repo audit (2026-11-12) found code that is shipped but not wired, code with no caller, and docs that contradict the code. This template is cloned by many teams: a half-wired capability misleads every clone, and an unused symbol is something every clone has to read. Rule for this change: a capability a product would expect to work is made to work; a symbol with no purpose is deleted. Broken route guards, stranded tasks and unsafe LLM defaults found by the same audit are a follow-up change.

Findings:

- `app/modules/messaging/webhooks/dispatcher.py:15`: `DEFAULT_WEBHOOK_RETRY_POLICY` exists but `dispatch()` (`:52-74`) sends once and never retries.
- `scripts/run_eval.py:70-89` (the gate CI runs) has its own loop over cases; `run_eval_cases` / `EvalReport` (`app/modules/ai/evals/runner.py:40-58,149-182`) are only reached by `tests/unit/modules/test_evals.py`. `run_eval.py:73-77` counts a mistyped `metadata.evaluator` as a skipped judge case.
- `app/core/config/__init__.py:39,79-96`: `Settings.redacted_summary` has no caller outside its test and is wrong: `MONGODB_URI` with credentials is shown, `LLM_MAX_TOKENS`, `IDEMPOTENCY_KEY_MAX_LENGTH` and `STREAM_FIRST_TOKEN_TIMEOUT_SECONDS` are masked.
- `app/core/errors.py:15-102`: `PYDANTIC_ERROR_MESSAGES` / `format_validation_errors` rewrite the `msg` of 422 errors and no test asserts any rewritten message.
- No caller anywhere: `ServerError`, `TokenError` (`app/core/errors.py:203,225`); `CircuitBreaker.reset`, `_error_retry_after` (`app/core/resilience.py:130,236`); `RetryPolicy.retry_exceptions` (`:87`, duplicates `retry_on`); `log = logger` and the `noisy_loggers` parameter (`app/core/logging.py:46,90`); `app/modules/messaging/webhooks/factory.py` (one line); `TaskRecord.metadata` (`app/modules/messaging/tasks/store.py:29`); `WorkerContext.settings`, `worker_context(addons=)`, `check_worker_configuration` and the `--check` argument (`app/bootstrap/worker.py:41,198,224`, `scripts/run_worker.py:29`), which repeat start-up validation; `app/modules/platform/rate_limit/factory.py` (pass-through); `if TYPE_CHECKING: pass` (`app/modules/platform/mongo/factory.py:9-10`).
- `pyproject.toml:34`: `openai` is never imported; `langchain-openai` already depends on it.
- `openspec/changes/archive/`: 90 files of completed-change history that nothing reads.
- Docs contradict the code: `docs/usage.md:7,73,114,265-267`, `docs/template-guide.md:35-40,52-53,101-106,190`, `README.md:21`, `docs/agents/ai-engineering.md:79,102`, `app/core/README.md`. Ignore and pre-commit files list paths that do not exist.

## What changes

1. Webhook dispatch retries. `HttpWebhookDispatcher.dispatch` retries per `DEFAULT_WEBHOOK_RETRY_POLICY`; `send_once` is the single attempt and the outbox sink uses it (the outbox owns its own retries). New setting `WEBHOOK_MAX_ATTEMPTS` (default 3). **BREAKING** (only when `WEBHOOKS_ENABLED=true` and product code calls `dispatch`): a failing endpoint is now called up to `WEBHOOK_MAX_ATTEMPTS` times and the call can take longer.
2. One eval loop. `scripts/run_eval.py` calls `run_eval_cases`; `EvalReport` carries skipped cases, pass rate and failures. **BREAKING** (eval datasets): an unknown `metadata.evaluator` fails the gate instead of being skipped.
3. Settings summary. `redacted_summary` masks by whole-word marker and by URL credentials, and the API and the worker log it once at start.
4. Validation messages keep their rewriting and get tests. No behaviour change.
5. Deletions: the no-caller symbols listed above. **BREAKING** (only for a clone that runs `python -m scripts.run_worker --check`): the argument is rejected like any unknown argument.
6. Repo: drop the `openai` pin, delete `openspec/changes/archive/` contents and `alembic/README`, fix the listed doc lines, fix ignore and pre-commit entries.

## Impact

- Setting added: `WEBHOOK_MAX_ATTEMPTS` (default 3, in `.env.example`). None removed or renamed.
- No migration. HTTP contract unchanged.
- Python API removed: the symbols in "What changes" 5. Python API added: `HttpWebhookDispatcher.send_once`, `EvalReport.skipped_cases` / `pass_rate` / `failures`.
- Not in this change: `require_quota` / `@idempotent` defects, stranded tasks, LLM defaults, eval gate grading only the echo handler, single-value backend settings, migration squash.
