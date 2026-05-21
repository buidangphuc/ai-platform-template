from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.request_context import get_request_id
from app.core.schema import format_validation_errors


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    data: Any = None


class BadRequestError(AppError):
    def __init__(
        self,
        message: str = "Bad request",
        *,
        code: str = "bad_request",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=400, data=data)


class UnauthorizedError(AppError):
    def __init__(
        self,
        message: str = "Unauthorized",
        *,
        code: str = "unauthorized",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=401, data=data)


class ForbiddenError(AppError):
    def __init__(
        self,
        message: str = "Forbidden",
        *,
        code: str = "forbidden",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=403, data=data)


class NotFoundError(AppError):
    def __init__(
        self,
        message: str = "Not found",
        *,
        code: str = "not_found",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=404, data=data)


class MethodNotAllowedError(AppError):
    def __init__(
        self,
        message: str = "Method not allowed",
        *,
        code: str = "method_not_allowed",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=405, data=data)


class ConflictError(AppError):
    def __init__(
        self,
        message: str = "Conflict",
        *,
        code: str = "conflict",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=409, data=data)


class UnprocessableEntityError(AppError):
    def __init__(
        self,
        message: str = "Unprocessable entity",
        *,
        code: str = "unprocessable_entity",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=422, data=data)


class RateLimitError(AppError):
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        code: str = "rate_limit_exceeded",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=429, data=data)


class ServerError(AppError):
    def __init__(
        self,
        message: str = "Internal server error",
        *,
        code: str = "internal_server_error",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=500, data=data)


class ServiceUnavailableError(AppError):
    def __init__(
        self,
        message: str = "Service unavailable",
        *,
        code: str = "service_unavailable",
        data: Any = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=503, data=data)


class TokenError(UnauthorizedError):
    def __init__(
        self,
        message: str = "Invalid or expired token",
        *,
        code: str = "invalid_token",
    ) -> None:
        super().__init__(message=message, code=code)


_HTTP_STATUS_CODE_MAP: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "unprocessable_entity",
    429: "rate_limit_exceeded",
    500: "internal_server_error",
    501: "not_implemented",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def _http_error_code(status_code: int) -> str:
    return _HTTP_STATUS_CODE_MAP.get(status_code, "http_error")


def _envelope(*, code: str, message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": get_request_id(),
    }
    if data is not None:
        payload["data"] = data
    return {"error": payload}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code=exc.code, message=exc.message, data=exc.data),
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = format_validation_errors(exc.errors())
    return JSONResponse(
        status_code=422,
        content=_envelope(
            code="validation_error",
            message="Request validation failed",
            data=jsonable_encoder(details),
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=_envelope(
            code=_http_error_code(exc.status_code),
            message=str(exc.detail),
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
