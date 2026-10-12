"""Readiness-delay server: /readyz goes 503 while the listener still accepts."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import time

import pytest
import uvicorn

from app import serve
from tests.factories import build_test_settings


async def _app(scope, receive, send) -> None:
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            else:
                await send({"type": "lifespan.shutdown.complete"})
                return


def _server(delay: float, drained: list[float]) -> serve.ReadinessDelayServer:
    config = uvicorn.Config(_app, port=0, lifespan="on", log_level="warning")
    server = serve.ReadinessDelayServer(
        config,
        begin_draining=lambda: drained.append(time.monotonic()),
        readiness_delay_seconds=delay,
    )
    server.capture_signals = contextlib.nullcontext  # type: ignore[method-assign]
    return server


async def _started(server: uvicorn.Server) -> None:
    while not server.started:
        await asyncio.sleep(0.01)


async def test_first_signal_marks_draining_then_exits_after_the_delay():
    drained: list[float] = []
    server = _server(0.4, drained)
    task = asyncio.create_task(server.serve())
    await _started(server)

    sent = time.monotonic()
    server.handle_exit(signal.SIGTERM, None)
    await asyncio.sleep(0.1)
    assert len(drained) == 1
    assert server.should_exit is False

    await asyncio.wait_for(task, timeout=5)
    assert time.monotonic() - sent >= 0.4


async def test_zero_delay_exits_immediately():
    drained: list[float] = []
    server = _server(0, drained)
    task = asyncio.create_task(server.serve())
    await _started(server)

    server.handle_exit(signal.SIGTERM, None)
    assert server.should_exit is True
    assert len(drained) == 1
    await asyncio.wait_for(task, timeout=5)


async def test_second_signal_skips_the_delay_and_forces_exit():
    drained: list[float] = []
    server = _server(30, drained)
    task = asyncio.create_task(server.serve())
    await _started(server)

    sent = time.monotonic()
    server.handle_exit(signal.SIGTERM, None)
    await asyncio.sleep(0.05)
    server.handle_exit(signal.SIGTERM, None)
    assert server.should_exit is True
    assert server.force_exit is True
    assert len(drained) == 1

    await asyncio.wait_for(task, timeout=5)
    assert time.monotonic() - sent < 5


def test_readiness_delay_is_bounded_and_defaults_to_five_seconds():
    assert build_test_settings().SHUTDOWN_READINESS_DELAY_SECONDS == 5
    assert build_test_settings(SHUTDOWN_READINESS_DELAY_SECONDS=0)
    with pytest.raises(ValueError):
        build_test_settings(SHUTDOWN_READINESS_DELAY_SECONDS=-1)
