from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class EvalScore:
    name: str
    value: bool | float | str
    data_type: str
    comment: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.value) if self.data_type == "BOOLEAN" else True


@runtime_checkable
class Evaluator(Protocol):
    name: str

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore: ...


class ExactMatchEvaluator:
    name = "exact_match"

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore:
        return EvalScore(
            name=self.name,
            value=output == expected,
            data_type="BOOLEAN",
        )


class ContainsEvaluator:
    name = "contains"

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore:
        return EvalScore(
            name=self.name,
            value=str(expected) in str(output),
            data_type="BOOLEAN",
        )


class JsonFieldEqualsEvaluator:
    def __init__(self, *, path: str, expected: Any) -> None:
        self.path = path
        self.expected = expected
        self.name = f"json_field_equals:{path}"

    def evaluate(self, *, output: Any, expected: Any) -> EvalScore:
        actual = _read_path(output, self.path)
        return EvalScore(
            name=self.name,
            value=actual == self.expected,
            data_type="BOOLEAN",
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
        return EvalScore(
            name=self.name,
            value=self._evaluate(output, expected),
            data_type="BOOLEAN",
        )


def _read_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
            continue
        return None
    return current
