from pathlib import Path

from app.modules.evals.evaluators import (
    ContainsEvaluator,
    ExactMatchEvaluator,
    JsonFieldEqualsEvaluator,
)
from app.modules.evals.runner import EvalCase, EvalTargetResult, run_eval_cases


class _FakeTracker:
    def __init__(self) -> None:
        self.scores: list[dict[str, object]] = []

    def score_trace(self, **kwargs):
        self.scores.append(kwargs)
        return kwargs


async def test_eval_runner_scores_cases_and_pushes_langfuse_scores():
    tracker = _FakeTracker()

    async def target(case: EvalCase) -> EvalTargetResult:
        return EvalTargetResult(output=case.input, trace_id=f"trace-{case.id}")

    report = await run_eval_cases(
        [
            EvalCase(id="one", input="hello world", expected="hello"),
            EvalCase(id="two", input="bye", expected="hello"),
        ],
        target=target,
        evaluators=[ContainsEvaluator()],
        tracker=tracker,
    )

    assert report.total_cases == 2
    assert report.total_scores == 2
    assert report.passed_scores == 1
    assert [score.value for result in report.results for score in result.scores] == [
        True,
        False,
    ]
    assert [score["trace_id"] for score in tracker.scores] == ["trace-one", "trace-two"]


async def test_eval_runner_skips_langfuse_score_without_trace_id():
    tracker = _FakeTracker()

    async def target(case: EvalCase) -> str:
        return case.input

    report = await run_eval_cases(
        [EvalCase(id="one", input="hello", expected="hello")],
        target=target,
        evaluators=[ExactMatchEvaluator()],
        tracker=tracker,
    )

    assert report.passed_scores == 1
    assert tracker.scores == []


async def test_json_field_evaluator_reads_nested_values():
    async def target(case: EvalCase) -> dict[str, object]:
        return {"data": {"status": "ok"}}

    report = await run_eval_cases(
        [EvalCase(id="one", input={}, expected={"status": "ok"})],
        target=target,
        evaluators=[JsonFieldEqualsEvaluator(path="data.status", expected="ok")],
    )

    assert report.results[0].scores[0].value is True


def test_load_eval_cases_from_jsonl(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"id":"one","input":"hello","expected":"hello","metadata":{"a":1}}\n',
        encoding="utf-8",
    )

    from app.modules.evals.runner import load_jsonl_cases

    cases = load_jsonl_cases(path)

    assert cases == [
        EvalCase(
            id="one",
            input="hello",
            expected="hello",
            metadata={"a": 1},
        )
    ]
