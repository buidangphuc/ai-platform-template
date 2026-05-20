import pytest

from app.adapters.mlops.mlflow import MLflowExperimentTracker
from app.contracts.experiment_tracker import ExperimentRunStatus


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
