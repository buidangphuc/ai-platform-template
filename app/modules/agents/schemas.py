from typing import Literal

from pydantic import BaseModel, Field

AgentRunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class AgentRequest(BaseModel):
    task: str
    input: dict[str, object] = Field(default_factory=dict)
    tools: list[dict[str, object]] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    name: str
    payload: dict[str, object] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    run_id: str
    status: AgentRunStatus
    output: dict[str, object] = Field(default_factory=dict)
    events: list[AgentEvent] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
