from datetime import UTC, datetime

from app.contracts.agents import AgentEvent, AgentRequest, AgentResponse
from app.contracts.artifacts import ArtifactManifest, ArtifactType
from app.contracts.experiment_tracker import (
    ExperimentRun,
    ExperimentRunStatus,
    MetricRecord,
)


def test_agent_contract_captures_runtime_agnostic_run_data():
    request = AgentRequest(
        task="answer with retrieval",
        input={"question": "What changed?"},
        tools=[{"name": "search", "description": "Search documents"}],
        metadata={"trace_id": "trace-1"},
    )
    event = AgentEvent(
        name="tool_call",
        payload={"tool": "search"},
    )
    response = AgentResponse(
        run_id="agent-run-1",
        status="completed",
        output={"answer": "Contract added."},
        events=[event],
    )

    assert request.task == "answer with retrieval"
    assert response.events[0].name == "tool_call"
    assert response.output["answer"] == "Contract added."


def test_experiment_tracker_contract_records_metrics_without_vendor_types():
    run = ExperimentRun(
        run_id="run-1",
        name="rag-eval",
        status=ExperimentRunStatus.SUCCEEDED,
        started_at=datetime(2026, 5, 20, tzinfo=UTC),
        ended_at=datetime(2026, 5, 20, 1, tzinfo=UTC),
        metadata={"dataset": "golden-v1"},
    )
    metric = MetricRecord(
        name="faithfulness",
        value=0.92,
        step=1,
        metadata={"judge": "local"},
    )

    assert run.status == ExperimentRunStatus.SUCCEEDED
    assert metric.value == 0.92


def test_artifact_manifest_contract_matches_promotion_rule():
    manifest = ArtifactManifest(
        name="rag-answer-prompt",
        version="2026.05.20",
        type=ArtifactType.PROMPT,
        owner="ai-platform",
        created_at=datetime(2026, 5, 20, tzinfo=UTC),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        runtime_dependencies=["app.contracts.llm"],
        eval_report="research/evaluation/reports/rag-answer.md",
        risk_notes=["Requires source attribution checks."],
        artifact_uri="research/prompts/rag-answer.yaml",
    )

    assert manifest.type == ArtifactType.PROMPT
    assert manifest.runtime_dependencies == ["app.contracts.llm"]
    assert manifest.eval_report.endswith("rag-answer.md")
