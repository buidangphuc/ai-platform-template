Working branch: `chore/platform-audit-remediation`. Sonnet worktree agents write all code (skill `openspec-fanout`).

## 1. Core: SSE helper, service observation, thin views (wave 1)

Owns: `app/api/sse.py` (new), `app/api/router.py`, `app/api/v1/completions/router.py`, delete `app/api/v1/completions/{observability,streaming,stream,sync}.py`, `app/modules/business/completions/service.py`, `app/modules/business/completions/schemas.py` (everything except the `COMPLETION_TASK_TYPE` line packet 2 appends at end of file), `app/core/telemetry.py`, `app/bootstrap/services.py`, `tests/unit/api/test_stream_disconnect.py`, new `tests/unit/api/test_sse.py`, new `tests/unit/modules/completions/test_service_observation.py`.

Contracts:
```python
# app/core/telemetry.py
class LogCompletionSink:   # emits today's exact "completion mode=..." log line (bind + message)
class FanOutSink:          # FanOutSink(sinks: Sequence[CompletionSink]); record_completion forwards to each
# app/modules/business/completions/service.py
@dataclass(frozen=True)
class StreamPolicy: first_token_timeout: float; idle_timeout: float
class StreamTimeoutError(AppError): code="stream_timeout", status 504
class CompletionService:
    def __init__(self, handler, *, guards=(), sink: CompletionSink, policy: StreamPolicy): ...
# app/modules/business/completions/schemas.py
class CompletionResponse: id: str = Field(default_factory=lambda: f"cmpl_{uuid4().hex}")
class StreamSummary(BaseModel): model, usage, finish_reason; def merge(chunk) -> None  # latest non-empty wins; insert right after CompletionUsage
# app/api/sse.py
SSE_HEADERS; PING = ": ping\n\n"
@dataclass(frozen=True) class ServerSentEvent: data: dict[str, object]; event: str | None = None; def encode(self) -> str  # json.dumps, same spacing as today
async def event_stream_response(request: Request, events: AsyncGenerator[ServerSentEvent, None]) -> StreamingResponse
# app/api/v1/completions/router.py
router = APIRouter(prefix="/completions", tags=["completions"], dependencies=[Depends(require_principal)])
tasks_router = APIRouter(prefix="/completions", tags=["completions"]); tasks_router.include_router(tasks.router)
```

- [ ] 1.1 `LogCompletionSink`, `FanOutSink`; verify a unit test that the log line is unchanged and fan-out reaches every sink
- [ ] 1.2 `CompletionService` records observations, applies `StreamPolicy` with `asyncio.timeout` per `anext`, outcome `disconnected` on `GeneratorExit`/`CancelledError`; verify `tests/unit/modules/completions/test_service_observation.py` (ok, error, timeout, first-token timeout, TTFT only for stream)
- [ ] 1.3 Bootstrap composes `FanOutSink([LogCompletionSink(), *([resources.telemetry] if resources.telemetry else [])])` and `StreamPolicy` from settings in `compose_business_services`; verify `tests/integration/test_completion_telemetry.py`
- [ ] 1.4 `app/api/sse.py` `event_stream_response`; verify `tests/unit/api/test_sse.py` (prime raises before headers, heartbeat, AppError code frame, generic `stream_error`, shielded close)
- [ ] 1.5 `router.py` holds the sync and stream views (stream view: local `_events(chunks)` yielding `content.delta` frames then the `done` frame from `StreamSummary`); delete the four old files; wire `app/api/router.py`; verify `tests/integration/test_completion_streaming.py`, `test_completion_patterns.py`, `test_completion_safety.py`, `tests/unit/core/test_application_wiring.py`
- [ ] 1.6 Rewrite `tests/unit/api/test_stream_disconnect.py`: disconnect under an anyio cancel scope → recording sink sees exactly `["disconnected"]`, handler `finally` runs

## 2. Completion tasks (wave 1)

Owns: `app/api/v1/completions/tasks.py`, `app/modules/messaging/tasks/service.py`, `app/bootstrap/worker.py` (message handler), `app/modules/business/completions/schemas.py` (append `COMPLETION_TASK_TYPE = "completion"` at end of file only), `tests/unit/modules/tasks/test_service.py`, task tests in `tests/integration/test_completion_patterns.py`, worker test file.

- [ ] 2.1 `require_owned(task_id, *, principal_id, type)`; verify not-found on type mismatch
- [ ] 2.2 `tasks.py` uses `COMPLETION_TASK_TYPE`, `TaskResponse.model_validate(task)`, `router = APIRouter()` without prefix or router-level dependency; verify `GET` of another type → 404
- [ ] 2.3 Worker stores `result.model_dump(mode="json")`; verify stored result has `usage` and `finish_reason`

## 3. Docs (wave 2)

Owns: `.agents/fastapi-template-repo/SKILL.md`, `.agents/fastapi-template-repo/references/architecture.md`, `.agents/senior-ai-engineer/references/ai-engineering.md`, `README.md` (completions/streaming sections only).

- [x] 3.1 "Canonical feature" section in SKILL.md: API package = `router.py` (+ gated `tasks.py`); view = read service → one call → `model_validate`; streaming only via `app/api/sse.py`; timing, deadlines, telemetry inside the service via ports composed in bootstrap
- [x] 3.2 Fix paths in `architecture.md` and `ai-engineering.md` (stream contract now `app/api/sse.py` + `CompletionService`)

## 4. Convention dry-run (wave 3, not merged)

- [ ] 4.1 A fresh agent with only `.agents/` and platform code, in a worktree where `app/api/v1/completions/` is deleted, rebuilds it from the skill; diff against packet 1+2 output. Every divergence becomes a docs fix in packet 3's files.
