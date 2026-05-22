from fastapi import Request

from app.api.v1.completions.handler import CompletionHandler
from app.bootstrap.state import optional_app_resource
from app.core.errors import AppError


def get_completion_handler(request: Request) -> CompletionHandler:
    handler = optional_app_resource(request.app, "completion_handler")
    if handler is None:
        raise AppError(
            code="completion_handler_not_configured",
            message="Completion handler is not configured",
            status_code=501,
        )
    return handler
