from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.types import ExceptionHandler

from app.core.request_context import get_request_id

PYDANTIC_ERROR_MESSAGES: dict[str, str] = {
    "bool_parsing": "Could not parse boolean value",
    "bool_type": "Expected a boolean",
    "bytes_too_long": "Bytes value is too long",
    "bytes_too_short": "Bytes value is too short",
    "bytes_type": "Expected bytes",
    "date_from_datetime_inexact": "Datetime must have zero time component",
    "date_from_datetime_parsing": "Could not parse date from datetime",
    "date_future": "Date must be in the future",
    "date_parsing": "Could not parse date",
    "date_past": "Date must be in the past",
    "date_type": "Expected a date",
    "datetime_future": "Datetime must be in the future",
    "datetime_object_invalid": "Invalid datetime object",
    "datetime_parsing": "Could not parse datetime",
    "datetime_past": "Datetime must be in the past",
    "datetime_type": "Expected a datetime",
    "decimal_max_digits": "Too many decimal digits",
    "decimal_max_places": "Too many decimal places",
    "decimal_parsing": "Could not parse decimal",
    "decimal_type": "Expected a decimal",
    "decimal_whole_digits": "Invalid decimal whole digits",
    "dict_type": "Expected a dictionary",
    "enum": "Invalid enum value, allowed values are {expected}",
    "extra_forbidden": "Extra fields are not allowed",
    "finite_number": "Expected a finite number",
    "float_parsing": "Could not parse float",
    "float_type": "Expected a float",
    "frozen_field": "Field is frozen and cannot be changed",
    "greater_than": "Value must be greater than {gt}",
    "greater_than_equal": "Value must be greater than or equal to {ge}",
    "int_from_float": "Expected an integer, got a float",
    "int_parsing": "Could not parse integer",
    "int_parsing_size": "Integer is out of range",
    "int_type": "Expected an integer",
    "invalid_key": "Invalid key",
    "is_instance_of": "Expected an instance of {class_name}",
    "json_invalid": "Invalid JSON: {error}",
    "json_type": "Expected a JSON value",
    "less_than": "Value must be less than {lt}",
    "less_than_equal": "Value must be less than or equal to {le}",
    "list_type": "Expected a list",
    "literal_error": "Expected one of: {expected}",
    "mapping_type": "Expected a mapping",
    "missing": "Field is required",
    "missing_argument": "Missing required argument",
    "model_attributes_type": "Invalid model attributes",
    "model_type": "Invalid model instance",
    "multiple_of": "Value must be a multiple of {multiple_of}",
    "none_required": "Value must be None",
    "set_type": "Expected a set",
    "string_pattern_mismatch": "String does not match pattern {pattern}",
    "string_too_long": "String is too long (max {max_length})",
    "string_too_short": "String is too short (min {min_length})",
    "string_type": "Expected a string",
    "time_parsing": "Could not parse time",
    "time_type": "Expected a time",
    "timezone_aware": "Datetime must include timezone information",
    "timezone_naive": "Datetime must not include timezone information",
    "too_long": "Value is too long",
    "too_short": "Value is too short",
    "tuple_type": "Expected a tuple",
    "url_parsing": "Could not parse URL",
    "url_scheme": "Invalid URL scheme",
    "url_syntax_violation": "URL has invalid syntax",
    "url_too_long": "URL is too long",
    "url_type": "Expected a URL",
    "uuid_parsing": "Could not parse UUID",
    "uuid_type": "Expected a UUID",
    "uuid_version": "Invalid UUID version",
    "value_error": "Invalid value",
}


def format_validation_errors(
    errors: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for error in errors:
        message_template = PYDANTIC_ERROR_MESSAGES.get(error.get("type", ""))
        if message_template:
            ctx = error.get("ctx") or {}
            try:
                error["msg"] = message_template.format(**ctx)
            except (KeyError, IndexError):
                error["msg"] = message_template
        formatted.append(error)
    return formatted


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    data: Any = None
    headers: dict[str, str] | None = None


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
        retry_after_seconds: int | None = None,
        data: Any = None,
    ) -> None:
        headers = (
            {"Retry-After": str(retry_after_seconds)}
            if retry_after_seconds is not None
            else None
        )
        super().__init__(
            code=code,
            message=message,
            status_code=429,
            data=data,
            headers=headers,
        )


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
        headers=exc.headers,
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
    app.add_exception_handler(AppError, cast(ExceptionHandler, app_error_handler))
    app.add_exception_handler(
        RequestValidationError,
        cast(ExceptionHandler, validation_error_handler),
    )
    app.add_exception_handler(
        HTTPException,
        cast(ExceptionHandler, http_exception_handler),
    )
