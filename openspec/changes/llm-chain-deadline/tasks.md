## 1. Chain deadline

- [x] 1.1 `LLM_CHAIN_DEADLINE_SECONDS` setting + validator + `.env.example`. Verify: `tests/unit/core/test_config.py::test_llm_chain_deadline_must_cover_one_call_timeout`, `check-env-example`
- [x] 1.2 `ainvoke` enforces the deadline, `LLMDeadlineExceeded`. Verify: `tests/unit/modules/test_llm_runtime.py` (`test_chain_deadline_stops_walking_*`, `test_deadline_error_is_a_transient_504`, `test_a_call_inside_the_deadline_is_unaffected`)
- [x] 1.3 Deadline-cut attempt not a breaker failure. Verify: `test_deadline_cut_attempt_does_not_count_against_its_breaker`
- [x] 1.4 `ai-engineering.md` model selection. Verify: read-through
