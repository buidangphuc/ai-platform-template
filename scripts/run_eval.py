"""Generic local eval smoke runner."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.modules.evals.evaluators import ContainsEvaluator, ExactMatchEvaluator
from app.modules.evals.runner import (
    EvalCase,
    EvalTargetResult,
    load_jsonl_cases,
    run_eval_cases,
)


async def _echo_target(case: EvalCase) -> EvalTargetResult:
    return EvalTargetResult(output=case.input)


def _default_cases() -> list[EvalCase]:
    return [
        EvalCase(id="exact", input="hello", expected="hello"),
        EvalCase(id="contains", input="hello world", expected="world"),
    ]


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    cases = load_jsonl_cases(args.cases) if args.cases else _default_cases()
    report = await run_eval_cases(
        cases,
        target=_echo_target,
        evaluators=[ExactMatchEvaluator(), ContainsEvaluator()],
    )
    return {
        "total_cases": report.total_cases,
        "total_scores": report.total_scores,
        "passed_scores": report.passed_scores,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True))


if __name__ == "__main__":
    main()
