## Why

`app/api/v1/completions/` is the template's reference feature, so AI-written features copy it. Review of PR #4 found it hand-rolls what the platform should provide:

- `observability.py` times, logs and records telemetry in the view (`CompletionTimer`, `completion_sink` = `resources.telemetry or NOOP_SINK`). The worker calls `CompletionService.complete` directly (`app/bootstrap/worker.py:129`), so task completions are never logged or measured.
- `streaming.py` is a 149-line SSE engine owned by one feature: first-token/idle deadlines, heartbeat, error frames and shielded cleanup. Deadlines are a model-call policy, not transport.
- `router.py` repeats the same prefix, tags and auth dependency three times; `tasks.py` also re-declares `require_principal`.
- `sync.py` mints the response id and copies result fields by hand; `tasks.py` copies ten task fields by hand.
- `TASK_TYPE = "completion"` lives in the API (`app/api/v1/completions/tasks.py:10`); `GET /completions/tasks/{id}` returns any task type the principal owns (`app/modules/messaging/tasks/service.py:117`).
- The worker stores only `content/model/metadata`, dropping `usage` and `finish_reason`.

## What Changes

- New shared API helper `app/api/sse.py`: SSE frame type, headers, heartbeat, priming (errors before the first event stay JSON errors), safe `event: error` frames, shielded close. Features stream through it; none owns an SSE engine.
- `CompletionService` owns observation and stream deadlines: it takes a `CompletionSink` and a `StreamPolicy`, records one `CompletionObservation` per call (`ok | error | timeout | disconnected`), and raises `StreamTimeoutError` (504, `stream_timeout`). API and worker share it.
- `app/core/telemetry.py` gains `LogCompletionSink` (today's log line, unchanged) and `FanOutSink`; bootstrap composes `FanOutSink([log, otel?])` once.
- `app/api/v1/completions/` shrinks to `router.py` (sync + stream views) and `tasks.py`; views read the service, call one method, and map with `model_validate`.
- Completion tasks are type-scoped (`COMPLETION_TASK_TYPE` in the business schemas) and the worker stores the full result.
- `.agents/fastapi-template-repo/SKILL.md` documents the canonical feature shape.

No BREAKING HTTP change: every endpoint, status code, SSE frame and log line keeps its shape. Internal break: `CompletionService(...)` gains `sink` and `policy` arguments (only bootstrap constructs it); `app.api.v1.completions.{observability,streaming,stream,sync}` are deleted.

## Impact

- Code: `app/api/sse.py` (new), `app/api/router.py`, `app/api/v1/completions/*`, `app/modules/business/completions/{service,schemas}.py`, `app/core/telemetry.py`, `app/bootstrap/services.py`, `app/bootstrap/worker.py`, `app/modules/messaging/tasks/service.py`.
- Tests: `tests/unit/api/test_stream_disconnect.py` rewritten; streaming, telemetry, patterns and safety integration tests keep passing unchanged.
- Docs: `.agents/fastapi-template-repo/{SKILL.md,references/architecture.md}`, `.agents/senior-ai-engineer/references/ai-engineering.md`.
