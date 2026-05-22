from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

from fastapi import FastAPI

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError

if TYPE_CHECKING:
    from app.bootstrap.resources import ApplicationResources

T = TypeVar("T")


def get_app_settings(app: FastAPI) -> Settings:
    settings = getattr(app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("app.state.settings is not configured")
    return settings


def optional_app_resource(app: FastAPI, name: str) -> Any | None:
    return getattr(app.state, name, None)


def require_app_resource(
    app: FastAPI,
    name: str,
    *,
    code: str,
    message: str,
) -> Any:
    resource = optional_app_resource(app, name)
    if resource is None:
        raise ServiceUnavailableError(message=message, code=code)
    return resource


def typed_app_resource(value: Any, expected_type: type[T]) -> T:
    return cast(T, value)


def attach_app_resource(
    app: FastAPI,
    resources: ApplicationResources,
    name: str,
    value: Any,
) -> None:
    setattr(app.state, name, value)
    if name not in resources.state_keys:
        resources.state_keys.append(name)


def clear_app_resource(app: FastAPI, name: str) -> None:
    if hasattr(app.state, name):
        delattr(app.state, name)
