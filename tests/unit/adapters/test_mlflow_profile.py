from types import SimpleNamespace

import pytest

from app.adapters.mlops import mlflow as mlflow_module
from app.adapters.mlops.mlflow import MLflowExperimentTracker
from app.contracts.experiment_tracker import ExperimentRunStatus, MetricRecord


async def test_mlflow_adapter_is_import_safe_and_requires_mlflow_dependency():
    tracker = MLflowExperimentTracker(tracking_uri="file:///tmp/mlruns")

    with pytest.raises(RuntimeError, match="mlflow is not installed"):
        await tracker.start_run("rag-eval")


def test_mlflow_profile_file_is_present():
    profile = "ops/mlops/mlflow.local.env.example"

    with open(profile, encoding="utf-8") as file:
        content = file.read()

    assert "MLFLOW_TRACKING_URI" in content
    assert "MLFLOW_EXPERIMENT_NAME" in content
    assert ExperimentRunStatus.SUCCEEDED.value == "succeeded"


async def test_mlflow_adapter_logs_against_active_run_without_reopening(
    monkeypatch,
):
    class FakeMLflow:
        def __init__(self) -> None:
            self.active = None
            self.metrics: list[tuple[str, float, int | None]] = []
            self.end_status: str | None = None
            self.start_calls: list[dict[str, object]] = []

        def set_tracking_uri(self, uri: str) -> None:
            self.tracking_uri = uri

        def set_experiment(self, name: str) -> None:
            self.experiment_name = name

        def start_run(self, **kwargs):
            if self.active is not None:
                raise RuntimeError("run already active")
            self.start_calls.append(kwargs)
            run_id = kwargs.get("run_id") or "run-1"
            self.active = SimpleNamespace(info=SimpleNamespace(run_id=run_id))
            return self.active

        def active_run(self):
            return self.active

        def set_tag(self, key: str, value: str) -> None:
            setattr(self.active, key, value)

        def log_metric(self, name: str, value: float, step: int | None = None) -> None:
            self.metrics.append((name, value, step))

        def log_artifact(self, uri: str) -> None:
            self.artifact_uri = uri

        def end_run(self, *, status: str) -> None:
            self.end_status = status
            self.active = None

    fake_mlflow = FakeMLflow()
    monkeypatch.setattr(mlflow_module, "find_spec", lambda name: object())
    monkeypatch.setitem(__import__("sys").modules, "mlflow", fake_mlflow)
    tracker = MLflowExperimentTracker(tracking_uri="file:///tmp/mlruns")

    run = await tracker.start_run("rag-eval")
    await tracker.log_metric(run.run_id, MetricRecord(name="score", value=1.0))
    ended = await tracker.end_run(run.run_id, status=ExperimentRunStatus.SUCCEEDED)

    assert fake_mlflow.start_calls == [{"run_name": "rag-eval"}]
    assert fake_mlflow.metrics == [("score", 1.0, None)]
    assert fake_mlflow.end_status == "FINISHED"
    assert ended.run_id == run.run_id
