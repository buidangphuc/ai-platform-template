"""API server entry point: ``python -m app.serve``.

uvicorn closes its listener the moment it receives SIGTERM and only then runs the
lifespan shutdown, so ``/readyz`` answering 503 while draining would never be seen
by a load balancer. This entry marks the app draining on the first signal, keeps
serving for ``SHUTDOWN_READINESS_DELAY_SECONDS`` so probes observe the 503, then
lets uvicorn's normal graceful shutdown run. A second signal skips the wait.
"""

from __future__ import annotations

import asyncio
import functools
import os
from collections.abc import Callable
from types import FrameType

import uvicorn
from uvicorn.importer import import_from_string

from app.bootstrap.state import get_health_service
from app.core.config import get_settings

APP_TARGET = "main:app"


class ReadinessDelayServer(uvicorn.Server):
    def __init__(
        self,
        config: uvicorn.Config,
        *,
        begin_draining: Callable[[], None],
        readiness_delay_seconds: float,
    ) -> None:
        super().__init__(config)
        self._begin_draining = begin_draining
        self._readiness_delay_seconds = readiness_delay_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._exit_timer: asyncio.TimerHandle | None = None
        self._draining = False

    async def serve(self, sockets=None) -> None:
        self._loop = asyncio.get_running_loop()
        await super().serve(sockets)

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        if self._draining:
            self._loop_call(self._cancel_exit_timer)
            self.force_exit = True
            super().handle_exit(sig, frame)
            return
        self._draining = True
        self._begin_draining()
        if self._loop is None or self._readiness_delay_seconds <= 0:
            super().handle_exit(sig, frame)
            return
        self._loop_call(self._arm_exit_timer, sig, frame)

    def _loop_call(self, callback: Callable[..., None], *args: object) -> None:
        # Signal handlers run outside the event loop's control flow.
        if self._loop is not None:
            self._loop.call_soon_threadsafe(callback, *args)

    def _arm_exit_timer(self, sig: int, frame: FrameType | None) -> None:
        assert self._loop is not None
        self._exit_timer = self._loop.call_later(
            self._readiness_delay_seconds,
            functools.partial(super().handle_exit, sig, frame),
        )

    def _cancel_exit_timer(self) -> None:
        if self._exit_timer is not None:
            self._exit_timer.cancel()


def main() -> None:
    settings = get_settings()
    app = import_from_string(APP_TARGET)
    config = uvicorn.Config(
        app,
        host=os.environ.get("SERVER_HOST", "0.0.0.0"),
        port=int(os.environ.get("SERVER_PORT", "8000")),
        loop="uvloop",
        http="httptools",
        access_log=False,
        timeout_graceful_shutdown=settings.GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
    )
    server = ReadinessDelayServer(
        config,
        begin_draining=lambda: get_health_service(app).begin_draining(),
        readiness_delay_seconds=settings.SHUTDOWN_READINESS_DELAY_SECONDS,
    )
    server.run()


if __name__ == "__main__":
    main()
