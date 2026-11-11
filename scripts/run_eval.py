"""Eval gate for the completions surface.

Runs the JSONL dataset against the CompletionService built by the completions
feature (echo handler by default — pass your product handler factory to
completions_feature when you fork) and FAILS (exit != 0)
when the pass rate drops below --min-score.

Per-case evaluator selection via metadata.evaluator: exact | contains |
judge. Judge cases need JUDGE_CHAT_MODEL (+ the [ai] extra); without it they
are SKIPPED so the gate stays hermetic in CI.

    python -m scripts.run_eval                    # default dataset + 0.8 gate
    python -m scripts.run_eval --cases evals/x.jsonl --min-score 0.9
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable

from app.bootstrap.features.completions import completions_feature
from app.bootstrap.resources import ApplicationResources
from app.core.config import get_settings
from app.modules.ai.evals.evaluators import (
    ContainsEvaluator,
    Evaluator,
    ExactMatchEvaluator,
    build_llm_judge,
)
from app.modules.ai.evals.runner import (
    EvalCase,
    EvalTargetResult,
    evaluate_one,
    load_jsonl_cases,
)
from app.modules.business.completions.schemas import CompletionRequest

DEFAULT_CASES = "evals/completions_smoke.jsonl"


def _build_target(settings) -> Callable[[EvalCase], Awaitable[EvalTargetResult]]:
    service = completions_feature().build(ApplicationResources(), settings)

    async def target(case: EvalCase) -> EvalTargetResult:
        result = await service.complete(CompletionRequest(**case.input))
        return EvalTargetResult(output=result.content)

    return target


def _build_evaluators(settings=None) -> dict[str, Evaluator | None]:
    settings = settings or get_settings()
    judge: Evaluator | None = None
    if settings.JUDGE_CHAT_MODEL:
        judge = build_llm_judge(settings)
    return {
        "exact": ExactMatchEvaluator(),
        "contains": ContainsEvaluator(),
        "judge": judge,
    }


async def _run(args: argparse.Namespace, settings=None) -> int:
    cases = load_jsonl_cases(args.cases)
    evaluators = _build_evaluators(settings)
    target = _build_target(settings or get_settings())

    scored = passed = skipped = 0
    failures: list[str] = []
    for case in cases:
        kind = case.metadata.get("evaluator", "exact")
        evaluator = evaluators.get(kind)
        if evaluator is None:
            skipped += 1
            continue
        target_result = await target(case)
        scores = await evaluate_one(
            output=target_result.output,
            expected=case.expected,
            evaluators=[evaluator],
        )
        for score in scores:
            scored += 1
            if score.passed:
                passed += 1
            else:
                failures.append(f"{case.id} [{score.name}] {score.comment or ''}")

    rate = (passed / scored) if scored else 0.0
    print(
        json.dumps(
            {
                "cases": len(cases),
                "scored": scored,
                "passed": passed,
                "skipped_judge": skipped,
                "pass_rate": round(rate, 4),
                "min_score": args.min_score,
                "failures": failures,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if rate >= args.min_score else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=DEFAULT_CASES)
    parser.add_argument("--min-score", type=float, default=0.8)
    args = parser.parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
