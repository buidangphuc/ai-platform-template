from __future__ import annotations

from typing import Any

import pytest

from app.modules.messaging.queue.gateway import QueueGateway


class SendFaults:
    def __init__(self, task_ids: set[str] | None) -> None:
        self.task_ids = task_ids
        self.active = True
        self.failed: list[str] = []

    def heal(self) -> None:
        self.active = False


def fail_sends(
    monkeypatch: pytest.MonkeyPatch,
    queue: QueueGateway,
    *,
    task_ids: set[str] | None = None,
) -> SendFaults:
    real_send = queue.send
    faults = SendFaults(task_ids)

    async def send(payload: dict[str, Any]) -> str:
        task_id = payload["task_id"]
        if faults.active and (faults.task_ids is None or task_id in faults.task_ids):
            faults.failed.append(task_id)
            raise ConnectionError("queue unavailable")
        return await real_send(payload)

    monkeypatch.setattr(queue, "send", send)
    return faults
