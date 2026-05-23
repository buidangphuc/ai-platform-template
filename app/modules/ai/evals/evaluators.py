from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class EvalScore:
    """A single evaluator outcome.

    ``passed`` is explicit: ``True`` = pass, ``False`` = fail, ``None`` = the
    evaluator does not produce a pass/fail signal (e.g. an unscored numeric
    metric used for trend tracking). Gating logic should treat ``False`` as
    "block" and ignore ``None``.
    """

    name: str
    value: bool | float | str
    data_type: str
    passed: bool | None = None
    comment: str | None = None


@runtime_checkable
class Evaluator(Protocol):
    """Sync or async evaluator.

    Implementations may return ``EvalScore`` directly or an awaitable
    (e.g. LLM-as-judge that calls an API). The runner awaits awaitable
    results before collecting scores.
    """

    name: str

    def evaluate(
        self, *, output: Any, expected: Any
    ) -> EvalScore | Awaitable[EvalScore]: ...


class ExactMatchEvaluator:
    name = "exact_match"

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore:
        match = output == expected
        return EvalScore(
            name=self.name,
            value=match,
            data_type="BOOLEAN",
            passed=match,
        )


class ContainsEvaluator:
    name = "contains"

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore:
        match = str(expected) in str(output)
        return EvalScore(
            name=self.name,
            value=match,
            data_type="BOOLEAN",
            passed=match,
        )


class JsonFieldEqualsEvaluator:
    def __init__(self, *, path: str, expected: Any) -> None:
        self.path = path
        self.expected = expected
        self.name = f"json_field_equals:{path}"

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore:
        actual = _read_path(output, self.path)
        match = actual == self.expected
        return EvalScore(
            name=self.name,
            value=match,
            data_type="BOOLEAN",
            passed=match,
            comment=f"{self.path}={actual!r}",
        )


class CallableEvaluator:
    def __init__(
        self,
        *,
        name: str,
        evaluate: Callable[[Any, Any], bool],
    ) -> None:
        self.name = name
        self._evaluate = evaluate

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore:
        result = self._evaluate(output, expected)
        return EvalScore(
            name=self.name,
            value=result,
            data_type="BOOLEAN",
            passed=bool(result),
        )


def _read_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
            continue
        return None
    return current
