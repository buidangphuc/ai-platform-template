from app.adapters.mlops.local_tracker import LocalExperimentTracker
from app.contracts.experiment_tracker import (
    ArtifactRecord,
    ExperimentRunStatus,
    MetricRecord,
)


async def test_local_experiment_tracker_persists_run_metrics_and_artifacts(tmp_path):
    tracker = LocalExperimentTracker(root=tmp_path)

    run = await tracker.start_run(
        "rag-eval",
        metadata={"dataset": "golden-sample"},
    )
    await tracker.log_metric(
        run.run_id,
        MetricRecord(name="keyword_hit_rate", value=1.0, step=1),
    )
    await tracker.log_artifact(
        run.run_id,
        ArtifactRecord(name="report", uri="research/evaluation/reports/rag-smoke.json"),
    )
    finished = await tracker.end_run(run.run_id, status=ExperimentRunStatus.SUCCEEDED)

    loaded = tracker.load_run(run.run_id)

    assert finished.status == ExperimentRunStatus.SUCCEEDED
    assert loaded.run.name == "rag-eval"
    assert loaded.metrics[0].name == "keyword_hit_rate"
    assert loaded.artifacts[0].name == "report"
    assert (tmp_path / "runs" / run.run_id / "run.json").exists()


async def test_local_experiment_tracker_lists_runs(tmp_path):
    tracker = LocalExperimentTracker(root=tmp_path)
    first = await tracker.start_run("first")
    second = await tracker.start_run("second")

    run_ids = [run.run_id for run in tracker.list_runs()]

    assert run_ids == [first.run_id, second.run_id]
