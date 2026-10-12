## 1. Resilience primitives

- [x] 1.1 `is_transient_error`, `error_status_code`, `retry_after_seconds`; breaker state machine with fake clock. Verify: `tests/unit/core/test_resilience.py` (`test_breaker_*`, `test_transient_statuses`, `test_deterministic_4xx_is_not_transient`)
- [x] 1.2 `RetryPolicy` capped exponential backoff, full jitter, `retry_on`, retry-after. Verify: `test_retry_policy_backoff_is_capped_exponential_with_full_jitter`, `test_retry_policy_honors_retry_after_hint_up_to_the_cap`, `test_retry_policy_default_retries_only_transient_errors`
- [x] 1.3 Outbox keeps retrying every sink error; webhook default policy fields. Verify: `test_outbox.py`, `test_webhooks.py`

## 2. LLM runtime

- [x] 2.1 Router: transient-only breaker, cooldown + probe, cached models, `failover_target`. Verify: `tests/unit/modules/test_llm_router.py`
- [x] 2.2 `LLMInstance` carries the router; `ainvoke` with failover. Verify: `tests/unit/modules/test_llm_runtime.py::test_ainvoke_fails_over_to_secondary_on_transient_primary_error`, `::test_ainvoke_does_not_fail_over_on_deterministic_error`
- [x] 2.3 Bounded provider calls: settings, `.env.example`, builder. Verify: `test_default_model_builder_passes_bounded_call_settings`, `check-env-example`
- [x] 2.4 Judge separation. Verify: `test_judge_equal_to_production_model_is_rejected_outside_local_env`, `test_judge_falls_back_to_chat_model_with_warning_in_local_env`
- [x] 2.5 Langfuse tracker typing. Verify: `tests/unit/modules/test_llm_langfuse.py`, pyright

## 3. Rate limiter

- [x] 3.1 Redis server-time windows. Verify: `tests/unit/modules/test_rate_limit.py::test_redis_rate_limiter_script_reads_redis_server_time`, `::test_redis_rate_limiter_pods_share_windows_via_server_clock`, `::test_redis_rate_limiter_lua_script_against_fakeredis` (needs `lupa`; skipped without it)

## 4. Docs

- [x] 4.1 `ai-engineering.md` model selection and open seam; `app/core/README.md` resilience. Verify: read-through
