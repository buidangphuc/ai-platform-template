from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": get_request_id(),
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
