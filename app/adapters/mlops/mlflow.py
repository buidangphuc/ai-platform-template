from datetime import UTC, datetime
from importlib.util import find_spec
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

    async def start_run(
        self,
        name: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> ExperimentRun:
        if find_spec("mlflow") is None:
            raise RuntimeError("mlflow is not installed")

        # Keep this adapter import-safe by importing MLflow only when enabled downstream.
        import mlflow  # type: ignore[import-not-found]

        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        active = mlflow.start_run(run_name=name)
        if metadata:
            for key, value in metadata.items():
                mlflow.set_tag(key, str(value))
        return ExperimentRun(
            run_id=active.info.run_id or str(uuid4()),
            name=name,
            status=ExperimentRunStatus.RUNNING,
            started_at=datetime.now(UTC),
            metadata=metadata or {},
        )

    async def log_metric(self, run_id: str, metric: MetricRecord) -> None:
        if find_spec("mlflow") is None:
            raise RuntimeError("mlflow is not installed")
        import mlflow  # type: ignore[import-not-found]

        with mlflow.start_run(run_id=run_id):
            mlflow.log_metric(metric.name, metric.value, step=metric.step)

    async def log_artifact(self, run_id: str, artifact: ArtifactRecord) -> None:
        if find_spec("mlflow") is None:
            raise RuntimeError("mlflow is not installed")
        import mlflow  # type: ignore[import-not-found]

        with mlflow.start_run(run_id=run_id):
            mlflow.log_artifact(artifact.uri)

    async def end_run(
        self,
        run_id: str,
        *,
        status: ExperimentRunStatus,
    ) -> ExperimentRun:
        if find_spec("mlflow") is None:
            raise RuntimeError("mlflow is not installed")
        import mlflow  # type: ignore[import-not-found]

        mlflow.end_run(
            status="FINISHED" if status == ExperimentRunStatus.SUCCEEDED else "FAILED"
        )
        return ExperimentRun(
            run_id=run_id,
            name=run_id,
            status=status,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
        )
