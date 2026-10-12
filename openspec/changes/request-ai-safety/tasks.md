## 1. Completions request contract and guard seam

Owns: `app/modules/business/completions/**`, `app/api/v1/completions/sync.py`, `app/bootstrap/services.py`, `evals/completions_smoke.jsonl`

- [x] 1.1 Client roles `user | assistant`, bounds, `extra="forbid"`; verify `tests/unit/modules/test_completion_schemas.py`, `test_system_role_is_422_validation_error`
- [x] 1.2 `usage` + `finish_reason` on result/response, echo fills them; verify `test_response_carries_usage_and_finish_reason`
- [x] 1.3 `CompletionGuard` / `GuardrailViolation`, `CompletionService(handler, guards)`, guards factory in composition; verify `test_guards_run_input_then_handler_then_output`, `test_guard_crash_fails_closed`, `test_guard_violation_maps_to_422_with_stable_code`

## 2. RAG, redaction, judge

- [x] 2.1 Delimited, untrusted retrieved text; `top_k` bound; verify `tests/unit/modules/test_rag_tool.py`
- [x] 2.2 Redaction gaps; verify `tests/unit/core/test_redaction.py`
- [x] 2.3 Judge prompt shape; verify `test_judge_prompt_delimits_output_and_criteria_as_data`

## 3. HTTP edge

- [x] 3.1 Catch-all exception handler; verify `test_unhandled_exception_returns_envelope_with_request_id`
- [x] 3.2 `TRUSTED_PROXY_COUNT`; verify `tests/unit/core/test_client_ip.py`

## 4. Docs

- [x] 4.1 Update "Cross-cutting requirements" and "Open seam: traces are NOT auto-redacted" in `.agents/senior-ai-engineer/references/ai-engineering.md`
