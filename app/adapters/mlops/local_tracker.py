import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from app.contracts.experiment_tracker import (
    ArtifactRecord,
    ExperimentRun,
    ExperimentRunStatus,
    MetricRecord,
)


class LocalRunRecord(BaseModel):
    run: ExperimentRun
    metrics: list[MetricRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


class LocalExperimentTracker:
    def __init__(self, *, root: str | Path = "research/experiments/local") -> None:
        self.root = Path(root)

    async def start_run(
        self,
        name: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> ExperimentRun:
        run = ExperimentRun(
            run_id=str(uuid4()),
            name=name,
            status=ExperimentRunStatus.RUNNING,
            started_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        self._write_record(LocalRunRecord(run=run))
        return run

    async def log_metric(self, run_id: str, metric: MetricRecord) -> None:
        record = self.load_run(run_id)
        record.metrics.append(metric)
        self._write_record(record)

    async def log_artifact(self, run_id: str, artifact: ArtifactRecord) -> None:
        record = self.load_run(run_id)
        record.artifacts.append(artifact)
        self._write_record(record)

    async def end_run(
        self,
        run_id: str,
        *,
        status: ExperimentRunStatus,
    ) -> ExperimentRun:
        record = self.load_run(run_id)
        record.run = record.run.model_copy(
            update={
                "status": status,
                "ended_at": datetime.now(UTC),
            },
        )
        self._write_record(record)
        return record.run

    def load_run(self, run_id: str) -> LocalRunRecord:
        path = self._run_path(run_id) / "run.json"
        return LocalRunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[ExperimentRun]:
        runs_dir = self.root / "runs"
        if not runs_dir.exists():
            return []
        runs = [
            self.load_run(path.name).run
            for path in sorted(runs_dir.iterdir())
            if path.is_dir()
        ]
        return sorted(runs, key=lambda run: run.started_at)

    def _write_record(self, record: LocalRunRecord) -> None:
        path = self._run_path(record.run.run_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "run.json").write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _run_path(self, run_id: str) -> Path:
        return self.root / "runs" / run_id
