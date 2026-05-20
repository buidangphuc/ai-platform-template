from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ExperimentRunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExperimentRun(BaseModel):
    run_id: str
    name: str
    status: ExperimentRunStatus
    started_at: datetime
    ended_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class MetricRecord(BaseModel):
    name: str
    value: float
    step: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ArtifactRecord(BaseModel):
    name: str
    uri: str
    metadata: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class ExperimentTracker(Protocol):
    async def start_run(
        self,
        name: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> ExperimentRun:
        raise NotImplementedError

    async def log_metric(self, run_id: str, metric: MetricRecord) -> None:
        raise NotImplementedError

    async def log_artifact(self, run_id: str, artifact: ArtifactRecord) -> None:
        raise NotImplementedError

    async def end_run(
        self,
        run_id: str,
        *,
        status: ExperimentRunStatus,
    ) -> ExperimentRun:
        raise NotImplementedError
