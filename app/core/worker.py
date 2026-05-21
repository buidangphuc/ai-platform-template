"""Generic async polling worker.

Pulls messages from any ``QueueGateway`` and dispatches them to a handler with
bounded concurrency, backpressure, and a SIGTERM-safe shutdown.  Wraps the
common production pattern of "claim N messages, fan out as tasks, ack on
success / nack on failure" so business code only writes the per-message
handler.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.modules.queue.gateway import QueueGateway, QueueMessage


MessageHandler = Callable[["QueueMessage"], Awaitable[None]]


class AsyncPollingWorker:
    def __init__(
        self,
        *,
        gateway: QueueGateway,
        handler: MessageHandler,
        max_concurrent: int = 10,
        poll_interval_seconds: float = 0.5,
        receive_batch_size: int = 10,
        receive_wait_seconds: float = 1.0,
    ) -> None:
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive")
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must not be negative")

        self.gateway = gateway
        self.handler = handler
        self.max_concurrent = max_concurrent
        self.poll_interval_seconds = poll_interval_seconds
        self.receive_batch_size = receive_batch_size
        self.receive_wait_seconds = receive_wait_seconds

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active: set[asyncio.Task[None]] = set()
        self._shutdown = asyncio.Event()

    def request_shutdown(self) -> None:
        self._shutdown.set()

    async def run(self) -> None:
        self._install_signal_handlers()
        logger.info(
            "worker.start max_concurrent={} poll_interval={}",
            self.max_concurrent,
            self.poll_interval_seconds,
        )

        try:
            while not self._shutdown.is_set():
                await self._tick()
        finally:
            await self._drain_active_tasks()
            await self.gateway.close()
            logger.info("worker.stopped")

    async def _tick(self) -> None:
        if len(self._active) >= self.max_concurrent * 2:
            await asyncio.sleep(self.poll_interval_seconds)
            return

        try:
            messages = await self.gateway.receive(
                max_messages=self.receive_batch_size,
                wait_seconds=self.receive_wait_seconds,
            )
        except Exception as exc:
            logger.exception("worker.receive_error: {}", exc)
            await asyncio.sleep(self.poll_interval_seconds)
            return

        for message in messages:
            task = asyncio.create_task(self._dispatch(message))
            self._active.add(task)
            task.add_done_callback(self._active.discard)

        if not messages:
            await asyncio.sleep(self.poll_interval_seconds)

    async def _dispatch(self, message: QueueMessage) -> None:
        async with self._semaphore:
            try:
                await self.handler(message)
                await self.gateway.ack(message)
            except Exception as exc:
                logger.exception(
                    "worker.handler_error message_id={} error={}",
                    message.id,
                    exc,
                )
                await self.gateway.nack(message, requeue=True)

    async def _drain_active_tasks(self) -> None:
        if not self._active:
            return
        logger.info("worker.draining active_tasks={}", len(self._active))
        await asyncio.gather(*list(self._active), return_exceptions=True)

    def _install_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        def _on_signal() -> None:
            logger.info("worker.signal_received")
            self._shutdown.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_: self._shutdown.set())
