from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WebhookEnvelope:
    id: str
    type: str
    occurred_at: datetime
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
            "metadata": self.metadata,
        }
