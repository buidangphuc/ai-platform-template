Execution: one wave of seven packets, each written by a Sonnet subagent in its own worktree branched from `fix/audit-defects`. A packet touches only its `Owns:` files. Files marked "shared" are edited by more than one packet: there a packet changes only the lines about its own topic (its settings, its tests, its doc section) so the commits merge. Each packet writes its named tests first and sees them fail, runs the checks in `docs/agents/project.md` "Checks" plus its own test files on localinfra (`uv run --env-file .env.test pytest <files>`), and makes one commit. The orchestrator reviews, cherry-picks, resolves shared-file conflicts and runs `make test-infra` after the wave.

## 1. Task delivery

Owns: `app/modules/messaging/tasks/**` (`outbox.py` is deleted), `app/bootstrap/worker.py`, `app/bootstrap/resources.py`, `app/core/config/messaging.py`, `tests/unit/modules/tasks/**`, `tests/integration/test_task_outbox_flow.py` (rename to `test_task_delivery_flow.py`), `tests/unit/core/test_config_messaging_rules.py`, `tests/unit/core/test_open_application_resources.py`, `tests/unit/core/test_bootstrap_state.py`, `docs/agents/architecture.md`, `alembic/versions/0011_*.py` (only if an index is needed). Shared: `.env.example` (TASKS_* lines), `tests/unit/test_run_worker_entry.py`, `tests/unit/core/test_config.py`, `docs/usage.md`, `docs/template-guide.md`, `README.md` (task and outbox sentences only).
Not yours: `app/modules/messaging/outbox/**` (the generic outbox stays as is), `ops/compose/**`.
Contract:
- `TaskStore.list_stale_queued(*, now, older_than_seconds, limit) -> list[TaskRef]`: selects QUEUED tasks with `updated_at < now - older_than_seconds` and `expires_at > now`, sets their `updated_at = now` in the same statement (Postgres: `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING`; Redis: atomic per key like `_transition`), returns them.
- `TaskStore.mark_completed(task_id, result) -> bool` and `mark_failed(task_id, error) -> bool`: apply only while status is PROCESSING; unknown id still raises `KeyError`. The Redis store routes both through the same atomic path as `_transition`.
- `TaskService` takes `queue: QueueGateway` instead of `dispatcher`; `submit` = `store.create` then send; `reclaim_stale_processing(...)` requeues stale PROCESSING tasks and announces them, then announces `list_stale_queued` results; a send failure on one task is logged and does not stop the others. `TaskDispatcher`, `QueueTaskDispatcher`, `PostgresTaskOutboxDispatcher`, `TaskQueueOutboxSink`, `TASK_EVENT_PREFIX`, `run_outbox_relay` are deleted.
- Settings: remove `TASKS_DISPATCH_BACKEND`, `TASKS_OUTBOX_RELAY_INTERVAL_SECONDS`, `TASKS_OUTBOX_RELAY_BATCH_SIZE` and their validator clauses; add `TASKS_QUEUED_REANNOUNCE_SECONDS: int = Field(default=60, gt=0)`.
- Worker: handler runs under `asyncio.timeout(service.lease_seconds)`; on `TimeoutError` the task is failed with error `lease_exceeded` and `NonRetryableMessageError` is raised; when `mark_completed` / `mark_failed` returns false the worker logs `worker.result_dropped` and returns normally.
- The cleanup loop keeps purging published outbox events when `OUTBOX_ENABLED`.

- [x] 1.1 Store conformance tests in `tests/unit/modules/tasks/conformance.py` (run for both stores): `test_list_stale_queued_returns_old_queued_and_bumps_updated_at`, `test_list_stale_queued_skips_fresh_expired_and_non_queued`, `test_mark_completed_is_refused_after_settlement`, `test_mark_failed_is_refused_after_settlement`; Redis only: `test_concurrent_settlements_apply_once`; verify red, implement, verify green on localinfra
- [x] 1.2 Service tests in `test_service.py`: `test_submit_send_failure_leaves_task_queued_and_sweep_announces_it`, `test_reclaim_send_failure_is_repaired_by_a_later_sweep`, `test_sweep_announces_a_stale_task_once_per_interval`, `test_one_failed_send_does_not_stop_the_sweep`; verify red, implement the single dispatch path, verify green
- [x] 1.3 Delete `tasks/outbox.py`, the relay loop, the dispatcher types and the three settings; `test_config_messaging_rules.py` gets `test_removed_dispatch_setting_is_rejected`; rewrite `test_task_outbox_flow.py` as `test_task_delivery_flow.py` (submit, worker run, lost announcement repaired); verify `rg "TASKS_DISPATCH_BACKEND|TASKS_OUTBOX_RELAY|run_outbox_relay|TaskQueueOutboxSink|PostgresTaskOutboxDispatcher" app tests scripts docs README.md .env.example` shows only the rejection test, and `python -m scripts.check_env_example`
- [x] 1.4 Worker tests in `test_run_worker_entry.py`: `test_handler_exceeding_the_lease_is_cancelled_and_task_failed`, `test_late_result_is_dropped_not_applied`; verify red, implement, verify green
- [x] 1.5 Docs: task delivery guarantees (at-least-once, handlers must be idempotent, lease bounds handler time, re-announce interval) in `docs/agents/architecture.md` and the task sections of `docs/usage.md` / `docs/template-guide.md`; remove every mention of the outbox dispatch mode

## 2. LLM safety

Owns: `app/core/config/ai.py`, `app/core/config/__init__.py`, `app/modules/ai/llm/router.py`, `app/modules/ai/llm/runtime.py`, `app/modules/ai/llm/langfuse.py`, `app/bootstrap/addons/llm.py`, `app/bootstrap/application.py`, `scripts/run_eval.py`, `tests/unit/modules/test_llm_router.py`, `tests/unit/modules/test_llm_runtime.py`, `tests/unit/modules/test_llm_langfuse.py`, `tests/unit/modules/completions/test_llm_observation.py`, `tests/unit/core/test_llm_addon.py`, `tests/unit/core/test_application_lifespan.py`, `tests/unit/test_run_eval_entry.py`, `docs/agents/ai-engineering.md`, `evals/README.md`. Shared: `.env.example` (LLM_* lines), `tests/unit/core/test_config.py`.
Contract: validators live where the architecture doc says (the mixin that owns the settings; the environment-dependent rule in `Settings.validate_runtime_safety`). `LlmAddon.open` pushes the flush onto its stack when Langfuse is enabled; `_flush_langfuse_client` and the lifespan branch are deleted. `scripts/run_eval.py::_build_target` opens the runtime with `open_runtime(settings, init_resources=True, addons=default_resource_addons(), features=FEATURES)` and reads `resources.service(CompletionService)`; keep the CLI, JSON keys and exit codes.

- [x] 2.1 `test_production_rejects_llm_enabled_without_chat_model`, `test_local_allows_fake_model_and_warns_once`; verify red, implement, verify green and that every existing test that relies on the fake model still passes
- [x] 2.2 `test_chain_deadline_must_cover_the_retry_budget`, `test_default_llm_settings_satisfy_the_budget_rule`; default `LLM_TIMEOUT_SECONDS=30` in settings and `.env.example`; `test_hung_primary_reaches_the_fallback_within_the_deadline` in `test_llm_runtime.py` (fake models and an injected clock, no real waiting); verify red then green. If the last test shows the runtime still cannot fail over on a hung primary with the new defaults, fix `runtime.py` so it does and say what you changed
- [x] 2.3 `test_first_token_stall_fails_over_and_counts_for_the_breaker`, `test_first_token_stall_without_fallback_raises_stream_timeout`; verify red, implement, verify green and the existing stream tests unchanged
- [x] 2.4 `test_llm_addon_flushes_langfuse_on_close`, `test_llm_addon_does_not_flush_when_langfuse_is_disabled` in `test_llm_addon.py`; move the flush; replace the lifespan flush tests in `test_application_lifespan.py` with one asserting the API still flushes through the addon; verify red then green
- [x] 2.5 `test_eval_gate_grades_the_model_backed_handler_when_llm_enabled`; verify red, implement, verify green and the hermetic gate command prints the same JSON as before
- [x] 2.6 Docs: `docs/agents/ai-engineering.md` (timeout budget rule, first-token failover, where the flush lives, what the gate grades), `evals/README.md`

## 3. Quota guard

Owns: `app/modules/platform/quota/**`, `app/bootstrap/addons/quota.py`, `tests/unit/modules/test_quota.py`, `tests/unit/modules/test_quota_mongo_store.py`, `tests/unit/modules/test_quota_postgres_store.py`, new `tests/integration/test_quota_guard.py`. Shared: `tests/integration/test_route_guards.py` (move the quota tests out to `test_quota_guard.py`; leave the idempotency tests untouched), `docs/usage.md` (quota guard paragraph and example only).
Contract: `require_quota(policy: QuotaPolicy, cost: int = 1)`; `QuotaService.reserve(*, subject_id, policy, cost=1, idempotency_key=None, ...)` and the other service methods take `policy` (required) instead of `resource` + optional policy; `build_quota_service(store)`; `QuotaPolicyStore` and `StaticQuotaPolicyStore` are deleted. `QuotaStore` protocol is unchanged except what the scenarios need. Mongo: `_migrate_active_counters` and its callers are deleted.

- [x] 3.1 `test_quota_guard.py`: `test_guard_works_with_the_shipped_addon` (app built with the quota addon, route with `require_quota(policy)`, limit reached gives 429 with `Retry-After`), `test_guard_reports_unavailable_when_quota_is_disabled`; verify red, implement the policy-carrying API, verify green
- [x] 3.2 Both adapters (parametrized or one test per store file): `test_retry_after_refund_charges_again`, `test_retry_after_refund_is_rejected_at_the_limit`; verify red, implement, verify green
- [x] 3.3 Mongo: `test_rejected_reserve_never_leaves_a_reservation`, `test_concurrent_same_key_reserves_charge_once`, `test_refund_never_drives_usage_below_zero`; verify red, reorder charge and insert, add the floor, delete the counter migration and its test; verify green
- [x] 3.4 Docs: `docs/usage.md` quota guard example with an explicit policy

## 4. Idempotent guard

Owns: `app/modules/platform/idempotency/**`, `tests/unit/modules/test_idempotency_http.py`, `tests/unit/modules/test_idempotency_store.py`, `tests/unit/modules/test_idempotency_postgres_store.py`. Shared: `tests/integration/test_route_guards.py` (idempotency tests only), `docs/usage.md` (`@idempotent` paragraph only).
Contract: the decorator reads the matched route from `request.scope["route"]` for `status_code` and `response_model`; the replayed and the stored body are the response-model-filtered JSON. A release path exists on the store/service (`release(...)` or equivalent) that removes or resets an in-progress claim owned by this request. Stored bodies may be any JSON value; if the column type cannot hold a non-object, wrap it in the storage layer without a migration and unwrap on replay.

- [x] 4.1 `test_failed_handler_releases_the_key`, `test_cancelled_handler_releases_the_key`; verify red, implement, verify green
- [x] 4.2 `test_replay_uses_the_declared_status_code`, `test_replay_is_filtered_by_the_response_model`, `test_list_body_is_stored_and_replayed`; verify red, implement, verify green
- [x] 4.3 `test_query_string_is_part_of_the_request_hash`; verify red, implement, verify green
- [x] 4.4 Docs: `docs/usage.md` `@idempotent` paragraph (what is replayed, what happens on failure)

## 5. HTTP edge

Owns: `app/core/config/infra.py`, `app/core/request_context.py`, `app/core/middleware.py`, `app/bootstrap/middleware.py`, `tests/unit/core/test_database.py`, `tests/unit/core/test_error_envelope.py`, `tests/integration/test_http_middleware.py`, `tests/integration/test_request_timeout.py`, `tests/integration/test_ip_rate_limit.py`, `tests/integration/test_gzip.py`, `tests/integration/test_unhandled_exception.py`, new `tests/unit/core/test_middleware_order.py`. Shared: `app/core/README.md` (middleware, request id and config/infra sections).
Contract: `POSTGRES_URL` stays a `str` computed field (`URL.create(...)` rendered with the password included); `alembic/env.py` and `app/core/database/engine.py` keep working with it. Exclude matching is one helper used by both middlewares. Middleware order as in `specs/core/http-edge/spec.md` (remember `add_middleware` makes the last added the outermost). `RequestIdMiddleware` stays outermost.

- [x] 5.1 `test_postgres_url_round_trips_reserved_characters` (build the password from parts so `detect-secrets` stays quiet); verify red, implement, verify green and `tests/unit/core/test_database.py` on localinfra
- [x] 5.2 `test_invalid_request_id_is_replaced`, `test_valid_request_id_is_kept`, `test_overlong_request_id_is_replaced`; verify red, implement, verify green
- [x] 5.3 `test_chunked_body_over_limit_gets_413`; verify red, implement, verify green
- [x] 5.4 `test_exclude_pattern_matches_whole_segments_only` for the timeout and the IP limiter; verify red, implement, verify green
- [x] 5.5 `test_middleware_order.py`: `test_timeout_is_access_logged_as_504`, `test_rate_limited_response_is_logged_and_has_cors_and_security_headers`, `test_preflight_does_not_consume_rate_limit_budget`, `test_body_limit_response_has_cors_headers`; verify red, reorder, verify green and every existing middleware integration test
- [x] 5.6 `app/core/README.md`: middleware order and the request-id rule

## 6. Storage safety

Owns: `app/core/redis.py`, `app/core/redaction.py`, `app/bootstrap/addons/cache.py`, `app/modules/platform/cache/**`, `app/modules/platform/objects/adapters/s3.py`, `tests/unit/modules/cache/**`, `tests/unit/modules/objects/**`, `tests/unit/core/test_redaction.py`. Shared: `app/core/README.md` (redis and redaction sections).
Contract: `build_redis_client(settings, *, decode_responses: bool = True)`; the cache addon opens `build_redis_client(settings, decode_responses=False)`, registers its close on the stack and does not use `resources.redis`; `_coerce_bytes` no longer needs to re-encode strings. S3 `list(prefix="", *, limit=100)` keeps its signature.

- [x] 6.1 `test_cache_addon_round_trips_non_utf8_bytes` (through the addon, `get` and `get_many`); verify red on localinfra, implement, verify green
- [x] 6.2 `test_list_excludes_sibling_prefixes`, `test_list_follows_continuation_tokens_up_to_limit`; verify red on localinfra, implement, verify green
- [x] 6.3 `test_decimals_and_dates_are_not_phone_numbers`, `test_token_count_fields_are_kept`, `test_non_string_mapping_key_does_not_raise`, `test_real_phone_numbers_are_still_redacted`; verify red, implement, verify green and every existing redaction test
- [x] 6.4 `app/core/README.md`: redis client option and redaction notes

## 7. Local stack

Owns: `ops/compose/**`, `ops/observability/**`, `Dockerfile`, `Makefile`. Shared: `docs/usage.md` and `docs/template-guide.md` (Docker and Langfuse paragraphs only), `README.md` (Docker lines only).
Contract: service name `migrate` (`command: alembic upgrade head`, same image and database env as the API); `api` and `worker` use `depends_on: migrate: condition: service_completed_successfully`. API port published as `127.0.0.1:8000:8000`. One image name, `ai-platform-template:local`, in compose and `make docker-build`. The overlay sets `UV_EXTRAS: ai` as a build arg for the API and worker. `x-task-env` drops `TASKS_DISPATCH_BACKEND`, `OUTBOX_ENABLED`, `OUTBOX_BACKEND` (tasks no longer use the outbox; another packet removes the setting).

- [x] 7.1 Edit the compose files and Makefile; verify `docker compose --project-directory . -f ops/compose/local.yaml config` and the same with `-f ops/compose/langfuse.yaml` exit 0 (use `--env-file .env.example`), and that the rendered config shows the `migrate` dependency, the loopback port and the build arg
- [x] 7.2 If Docker is available, `docker compose ... build api` for the base file; report the result, or that it could not run. Start no long-running stack
- [x] 7.3 Docs: the Docker and Langfuse paragraphs say what the stack runs, that migrations run automatically, which settings (`LLM_ENABLED`, `CHAT_MODEL`, `LANGFUSE_*`) produce a trace, and that the API listens on loopback
