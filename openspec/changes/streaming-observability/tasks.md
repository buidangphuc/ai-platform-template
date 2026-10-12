## 1. Stream contract

Owns: `app/api/v1/completions/**`, `app/modules/business/completions/{ports,service,schemas,handlers/echo}.py`, `app/core/config/http.py`, `.env.example`

- [x] 1.1 Narrow the stream port, delete `normalize_stream_chunk`, optional `model`/`usage`/`finish_reason` on chunks; verify `test_echo_stream_yields_one_chunk_carrying_usage_and_finish_reason`, `test_done_event_carries_usage_finish_reason_and_model`
- [x] 1.2 Prime the stream before the response; verify `test_input_guard_violation_is_a_json_422_not_a_200_stream`, `test_handler_startup_error_is_a_json_error_not_a_200_stream`
- [x] 1.3 SSE headers, heartbeat, error event; verify `test_stream_sets_sse_headers`, `test_heartbeat_comment_is_sent_while_waiting_for_the_next_chunk`, `test_mid_stream_exception_emits_a_safe_error_event_then_closes`
- [x] 1.4 Deadlines; verify `test_first_token_timeout_is_a_504_json_error`, `test_idle_timeout_after_first_chunk_is_an_error_event`, `test_streaming_deadlines_have_safe_defaults_and_bounds`
- [x] 1.5 Completion log line; verify `test_stream_logs_one_completion_line_without_content`, `test_sync_completion_logs_one_line_with_usage`

## 2. Shutdown and Langfuse

Owns: `app/core/health.py`, `app/bootstrap/application.py`, `app/core/config/runtime.py`, `Dockerfile`

- [x] 2.1 Draining readiness; verify `test_readiness_is_503_while_draining_and_liveness_stays_ok`, `test_draining_service_reports_not_ready_without_running_checks`
- [x] 2.2 Graceful default and Dockerfile timeout; verify `test_graceful_shutdown_is_on_by_default`
- [x] 2.3 Single typed Langfuse flush; verify `tests/unit/core/test_application_lifespan.py`

## 3. Request-id propagation

Owns: `app/modules/messaging/tasks/{message,service,outbox}.py`, `app/api/v1/completions/tasks.py`, `app/bootstrap/worker.py` (message handler only)

- [x] 3.1 `TaskMessage.request_id`; verify `test_request_id_is_optional_and_round_trips`, `test_request_id_must_be_a_non_empty_string_when_present`
- [x] 3.2 Submit forwards it; verify `test_submit_forwards_request_id_into_the_queue_message`
- [x] 3.3 Worker sets the ContextVar; verify `test_worker_handler_runs_the_task_under_the_submitting_request_id`

## 4. Docs

- [x] 4.1 README completions section, completions section of `.agents/senior-ai-engineer/references/ai-engineering.md`
