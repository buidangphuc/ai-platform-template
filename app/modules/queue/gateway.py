"""Backend-agnostic message queue contract.

Implementations live under ``app/modules/queue/adapters/`` and are selected via
``QUEUE_BACKEND`` at boot.  The protocol intentionally mirrors the lowest
common denominator of SQS / RabbitMQ / Redis Streams — receive, ack, nack —
so business code can swap backends without touching call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class QueueMessage:
    id: str
    body: dict[str, Any]
    receive_count: int = 1
    raw: Any = field(default=None, repr=False, compare=False)


@runtime_checkable
class QueueGateway(Protocol):
    async def send(self, payload: dict[str, Any]) -> str: ...

    async def receive(
        self,
        *,
        max_messages: int = 10,
        wait_seconds: float = 0.0,
    ) -> list[QueueMessage]: ...

    async def ack(self, message: QueueMessage) -> None: ...

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None: ...

    async def close(self) -> None: ...
