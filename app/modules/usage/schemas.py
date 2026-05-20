from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


class UsageRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    operation: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost: float = 0.0
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
