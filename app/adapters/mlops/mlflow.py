from datetime import UTC, datetime
from importlib.util import find_spec
from types import ModuleType
from uuid import uuid4

from app.contracts.experiment_tracker import (
    ArtifactRecord,
    ExperimentRun,
    ExperimentRunStatus,
    MetricRecord,
)


class MLflowExperimentTracker:
    def __init__(
        self,
        *,
        tracking_uri: str,
        experiment_name: str = "ai-platform-template",
    ) -> None:
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        self._runs: dict[str, ExperimentRun] = {}

    async def start_run(
        self,
        name: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> ExperimentRun:
        mlflow = self._mlflow()

        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        active = mlflow.start_run(run_name=name)
        if metadata:
            for key, value in metadata.items():
                mlflow.set_tag(key, str(value))
        run = ExperimentRun(
            run_id=active.info.run_id or str(uuid4()),
            name=name,
            status=ExperimentRunStatus.RUNNING,
            started_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        self._runs[run.run_id] = run
        return run

    async def log_metric(self, run_id: str, metric: MetricRecord) -> None:
        mlflow = self._mlflow()
        started = self._ensure_active_run(mlflow, run_id)
        try:
            mlflow.log_metric(metric.name, metric.value, step=metric.step)
        finally:
            if started:
                mlflow.end_run()

    async def log_artifact(self, run_id: str, artifact: ArtifactRecord) -> None:
        mlflow = self._mlflow()
        started = self._ensure_active_run(mlflow, run_id)
        try:
            mlflow.log_artifact(artifact.uri)
        finally:
            if started:
                mlflow.end_run()

    async def end_run(
        self,
        run_id: str,
        *,
        status: ExperimentRunStatus,
    ) -> ExperimentRun:
        mlflow = self._mlflow()
        self._ensure_active_run(mlflow, run_id)

        mlflow.end_run(
            status="FINISHED" if status == ExperimentRunStatus.SUCCEEDED else "FAILED"
        )
        existing_run = self._runs.get(run_id)
        ended_at = datetime.now(UTC)
        if existing_run is None:
            return ExperimentRun(
                run_id=run_id,
                name=run_id,
                status=status,
                started_at=ended_at,
                ended_at=ended_at,
            )
        ended_run = existing_run.model_copy(
            update={
                "status": status,
                "ended_at": ended_at,
            }
        )
        self._runs[run_id] = ended_run
        return ended_run

    def _mlflow(self) -> ModuleType:
        if find_spec("mlflow") is None:
            raise RuntimeError("mlflow is not installed")
        # Keep this adapter import-safe by importing MLflow only when enabled downstream.
        import mlflow  # type: ignore[import-not-found]

        return mlflow

    def _ensure_active_run(self, mlflow: ModuleType, run_id: str) -> bool:
        active_run = mlflow.active_run()
        if active_run is not None and active_run.info.run_id == run_id:
            return False
        mlflow.start_run(run_id=run_id)
        return True
