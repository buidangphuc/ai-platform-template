import asyncio
from pathlib import Path

import pytest

from app.core.resilience import TimeoutPolicy
from app.modules.ai.evals.evaluators import (
    CallableEvaluator,
    ContainsEvaluator,
    EvalScore,
    ExactMatchEvaluator,
    JsonFieldEqualsEvaluator,
)
from app.modules.ai.evals.runner import (
    EvalCase,
    EvalTargetResult,
    evaluate_one,
    load_jsonl_cases,
    push_scores_to_tracker,
    run_eval_cases,
)


class _FakeTracker:
    def __init__(self) -> None:
        self.scores: list[dict[str, object]] = []

    def score_trace(self, **kwargs):
        self.scores.append(kwargs)
        return kwargs


# ---------------------------------------------------------------- evaluators


def test_exact_match_evaluator_sets_explicit_passed():
    score = ExactMatchEvaluator().evaluate(output="hello", expected="hello")
    assert score.value is True
    assert score.passed is True

    score = ExactMatchEvaluator().evaluate(output="hello", expected="bye")
    assert score.value is False
    assert score.passed is False


def test_contains_evaluator_sets_explicit_passed():
    score = ContainsEvaluator().evaluate(output="hello world", expected="hello")
    assert score.passed is True

    score = ContainsEvaluator().evaluate(output="bye", expected="hello")
    assert score.passed is False


def test_json_field_equals_evaluator_includes_comment_and_passed():
    score = JsonFieldEqualsEvaluator(path="data.status", expected="ok").evaluate(
        output={"data": {"status": "ok"}},
        expected=None,
    )
    assert score.passed is True
    assert score.comment == "data.status='ok'"


def test_callable_evaluator_coerces_passed_from_truthy_value():
    evaluator = CallableEvaluator(
        name="non_empty",
        evaluate=lambda output, expected: bool(output),
    )
    assert evaluator.evaluate(output="x", expected=None).passed is True
    assert evaluator.evaluate(output="", expected=None).passed is False


def test_eval_score_passed_defaults_to_none_when_not_applicable():
    score = EvalScore(name="latency_ms", value=120.0, data_type="NUMERIC")
    assert score.passed is None


# ---------------------------------------------------------------- evaluate_one


async def test_evaluate_one_returns_scores_for_each_evaluator():
    scores = await evaluate_one(
        output="hello world",
        expected="hello",
        evaluators=[ContainsEvaluator(), ExactMatchEvaluator()],
    )

    assert [s.name for s in scores] == ["contains", "exact_match"]
    assert [s.passed for s in scores] == [True, False]


async def test_evaluate_one_supports_async_evaluator_and_timeout():
    """Async evaluators (e.g. LLM-as-judge) get awaited and respect timeout."""

    class _SlowAsyncEvaluator:
        name = "slow_async"

        async def evaluate(self, *, output, expected):
            await asyncio.sleep(0.5)
            return EvalScore(
                name=self.name, value=True, data_type="BOOLEAN", passed=True
            )

    with pytest.raises(asyncio.TimeoutError):
        await evaluate_one(
            output="x",
            expected=None,
            evaluators=[_SlowAsyncEvaluator()],
            timeout=TimeoutPolicy(timeout_seconds=0.05),
        )


async def test_evaluate_one_awaits_async_evaluators_when_not_timed_out():
    class _AsyncEvaluator:
        name = "async_ok"

        async def evaluate(self, *, output, expected):
            return EvalScore(
                name=self.name,
                value=output == expected,
                data_type="BOOLEAN",
                passed=output == expected,
            )

    scores = await evaluate_one(
        output="hello",
        expected="hello",
        evaluators=[_AsyncEvaluator()],
    )
    assert scores[0].passed is True


# ---------------------------------------------------------------- runner


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
    assert report.results[0].scores[0].passed is True


def test_load_eval_cases_from_jsonl(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"id":"one","input":"hello","expected":"hello","metadata":{"a":1}}\n',
        encoding="utf-8",
    )

    cases = load_jsonl_cases(path)

    assert cases == [
        EvalCase(
            id="one",
            input="hello",
            expected="hello",
            metadata={"a": 1},
        )
    ]


# ---------------------------------------------------------------- push helper


def test_push_scores_to_tracker_forwards_each_score():
    tracker = _FakeTracker()
    scores = [
        EvalScore(name="a", value=True, data_type="BOOLEAN", passed=True),
        EvalScore(name="b", value=0.9, data_type="NUMERIC"),
    ]

    push_scores_to_tracker(
        tracker,
        trace_id="trace-1",
        observation_id="obs-1",
        scores=scores,
    )

    assert [s["name"] for s in tracker.scores] == ["a", "b"]
    assert all(s["trace_id"] == "trace-1" for s in tracker.scores)
    assert all(s["observation_id"] == "obs-1" for s in tracker.scores)


# ---------------------------------------------------------------- gating shape


async def test_gating_pattern_a_raises_on_failed_score():
    """Demonstrates Pattern A.1/A.3: caller raises when passed is False."""
    scores = await evaluate_one(
        output="hello bye",
        expected="forbidden",
        evaluators=[ContainsEvaluator()],
    )

    failed = [s for s in scores if s.passed is False]

    assert len(failed) == 1
    assert failed[0].name == "contains"
