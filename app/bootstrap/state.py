from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from app.core.errors import ServiceUnavailableError

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.bootstrap.resources import ApplicationResources
    from app.core.config import Settings
    from app.core.health import HealthService
    from app.core.middleware import InFlightTracker

T = TypeVar("T")


def get_app_settings(app: FastAPI) -> Settings:
    return app.state.settings


def get_app_resources(app: FastAPI) -> ApplicationResources:
    return app.state.resources


def get_health_service(app: FastAPI) -> HealthService:
    return app.state.health_service


def get_in_flight_tracker(app: FastAPI) -> InFlightTracker | None:
    return app.state.in_flight_tracker


def require(value: T | None, *, code: str, message: str) -> T:
    if value is None:
        raise ServiceUnavailableError(code=code, message=message)
    return value
