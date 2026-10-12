"""Guardrail seam for the completion service (fail-closed).

A guard inspects the request before the handler runs and/or the result after.
It signals a policy hit by raising ``GuardrailViolation`` (HTTP 422, stable
code). Any other exception from a guard also aborts the request: a guard that
cannot decide never lets the content through.
"""

from typing import Protocol

from app.core.errors import UnprocessableEntityError
from app.modules.business.completions.schemas import CompletionRequest, CompletionResult

INPUT_VIOLATION_CODE = "guardrail_input_violation"
OUTPUT_VIOLATION_CODE = "guardrail_output_violation"


class GuardrailViolation(UnprocessableEntityError):
    def __init__(
        self,
        message: str = "Request blocked by guardrail",
        *,
        code: str = INPUT_VIOLATION_CODE,
        data: object = None,
    ) -> None:
        super().__init__(message, code=code, data=data)


class CompletionGuard(Protocol):
    async def check_input(self, request: CompletionRequest) -> None: ...

    async def check_output(
        self,
        request: CompletionRequest,
        result: CompletionResult,
    ) -> None: ...
