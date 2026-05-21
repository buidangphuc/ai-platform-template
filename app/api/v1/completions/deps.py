from fastapi import Request

from app.api.v1.completions.handler import CompletionHandler
from app.core.errors import AppError


def get_completion_handler(request: Request) -> CompletionHandler:
    handler = getattr(request.app.state, "completion_handler", None)
    if handler is None:
        raise AppError(
            code="completion_handler_not_configured",
            message="Completion handler is not configured",
            status_code=501,
        )
    return handler
