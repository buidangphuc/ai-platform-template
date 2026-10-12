"""Completions SSE: pre-flight errors, headers, heartbeat, deadlines, error events."""

import asyncio
import json
from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.bootstrap.application import create_app
from app.modules.business.completions.guards import GuardrailViolation
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
    CompletionUsage,
)
from tests.factories import build_test_settings

HEADERS = {"Authorization": "Bearer test-token"}
BODY = {"messages": [{"role": "user", "content": "hello"}]}
URL = "/api/v1/completions/stream"


class _Handler:
    """Scripted handler: ``steps`` are chunks, floats (sleep) or exceptions."""

    def __init__(self, *steps: CompletionStreamChunk | float | Exception) -> None:
        self.steps = steps

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(content="done", model="scripted")

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionStreamChunk]:
        for step in self.steps:
            if isinstance(step, CompletionStreamChunk):
                yield step
            elif isinstance(step, Exception):
                raise step
            else:
                await asyncio.sleep(step)


class _BlockInput:
    async def check_input(self, request: CompletionRequest) -> None:
        raise GuardrailViolation("blocked")

    async def check_output(
        self, request: CompletionRequest, result: CompletionResult
    ) -> None:
        return None


def _chunk(delta: str, **fields: object) -> CompletionStreamChunk:
    return CompletionStreamChunk(delta=delta, **fields)  # type: ignore[arg-type]


async def _post(
    handler, *, guards=(), logs: list[str] | None = None, **settings: object
):
    app = create_app(
        settings=build_test_settings(**settings),
        completion_handler_factory=lambda resources, s: handler,
        completion_guards_factory=lambda resources, s: guards,
        init_resources=False,
    )
    # After create_app: configure_logging() resets every loguru sink.
    sink = None if logs is None else logger.add(logs.append, format="{message}")
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                return await _stream(client)
    finally:
        if sink is not None:
            logger.remove(sink)


async def _stream(client: AsyncClient):
    async with client.stream("POST", URL, headers=HEADERS, json=BODY) as response:
        await response.aread()
    return response


def _events(response) -> list[tuple[str | None, dict]]:
    events: list[tuple[str | None, dict]] = []
    for frame in response.text.split("\n\n"):
        name, data = None, None
        for line in frame.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if data is not None:
            events.append((name, data))
    return events


async def test_stream_sets_sse_headers():
    response = await _post(_Handler(_chunk("hi")))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


async def test_input_guard_violation_is_a_json_422_not_a_200_stream():
    response = await _post(_Handler(_chunk("hi")), guards=(_BlockInput(),))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "guardrail_input_violation"


async def test_handler_startup_error_is_a_json_error_not_a_200_stream():
    response = await _post(_Handler(RuntimeError("upstream boom sk-secret")))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_server_error"
    assert "sk-secret" not in response.text


async def test_first_token_timeout_is_a_504_json_error():
    response = await _post(
        _Handler(5.0, _chunk("late")),
        STREAM_FIRST_TOKEN_TIMEOUT_SECONDS=0.1,
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "stream_timeout"


async def test_idle_timeout_after_first_chunk_is_an_error_event():
    response = await _post(
        _Handler(_chunk("first"), 5.0, _chunk("late")),
        STREAM_IDLE_TIMEOUT_SECONDS=0.15,
        SSE_HEARTBEAT_SECONDS=0.05,
    )

    assert response.status_code == 200
    events = _events(response)
    assert events[0][1]["delta"] == "first"
    assert events[-1] == ("error", {"type": "error", "code": "stream_timeout"})
    assert not any(data["type"] == "done" for _, data in events)


async def test_mid_stream_exception_emits_a_safe_error_event_then_closes():
    response = await _post(
        _Handler(_chunk("part"), RuntimeError("upstream boom sk-secret"))
    )

    assert response.status_code == 200
    events = _events(response)
    assert events[-1] == ("error", {"type": "error", "code": "stream_error"})
    assert "sk-secret" not in response.text
    assert "Traceback" not in response.text


async def test_heartbeat_comment_is_sent_while_waiting_for_the_next_chunk():
    response = await _post(
        _Handler(_chunk("a"), 0.3, _chunk("b")),
        SSE_HEARTBEAT_SECONDS=0.05,
        STREAM_IDLE_TIMEOUT_SECONDS=5,
    )

    assert response.text.count(": ping\n\n") >= 2
    deltas = [d["delta"] for _, d in _events(response) if d["type"] == "content.delta"]
    assert deltas == ["a", "b"]


async def test_done_event_carries_usage_finish_reason_and_model():
    usage = CompletionUsage(input_tokens=2, output_tokens=3, total_tokens=5)
    response = await _post(
        _Handler(
            _chunk("a"),
            _chunk("", usage=usage, finish_reason="stop", model="scripted"),
        )
    )

    assert _events(response)[-1][1] == {
        "type": "done",
        "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        "finish_reason": "stop",
        "model": "scripted",
    }


async def test_default_echo_stream_reports_usage(client: AsyncClient):
    response = await _stream(client)

    done = _events(response)[-1][1]
    assert done["type"] == "done"
    assert done["finish_reason"] == "stop"
    assert done["usage"] == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}


async def test_stream_logs_one_completion_line_without_content():
    lines: list[str] = []
    usage = CompletionUsage(input_tokens=2, output_tokens=3, total_tokens=5)
    await _post(
        _Handler(
            _chunk("secret-output"),
            _chunk("", usage=usage, finish_reason="stop", model="scripted"),
        ),
        logs=lines,
    )

    [line] = [ln for ln in lines if "completion " in ln and "mode=stream" in ln]
    for expected in (
        "outcome=ok",
        "model=scripted",
        "finish_reason=stop",
        "input_tokens=2",
        "output_tokens=3",
        "total_tokens=5",
        "duration_ms=",
        "ttft_ms=",
    ):
        assert expected in line
    assert "secret-output" not in line and "hello" not in line


async def test_sync_completion_logs_one_line_with_usage(client: AsyncClient):
    lines: list[str] = []
    sink = logger.add(lines.append, format="{message}")
    try:
        response = await client.post("/api/v1/completions", headers=HEADERS, json=BODY)
    finally:
        logger.remove(sink)

    assert response.status_code == 200
    [line] = [ln for ln in lines if "completion " in ln and "mode=sync" in ln]
    assert "outcome=ok" in line
    assert "model=echo" in line
    assert "finish_reason=stop" in line
    assert "total_tokens=3" in line
    assert "ttft_ms=None" in line
    assert "echo:" not in line
