import pytest
from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import (
    get_app_resources,
    get_app_settings,
    get_health_service,
    get_in_flight_tracker,
    require,
)
from app.core.errors import ServiceUnavailableError
from app.core.health import HealthService
from app.core.middleware import InFlightTracker
from tests.factories import build_test_settings


def test_get_app_settings_reads_configured_settings() -> None:
    app = FastAPI()
    settings = build_test_settings()
    app.state.settings = settings

    assert get_app_settings(app) is settings


def test_get_app_resources_returns_attached_container() -> None:
    app = FastAPI()
    resources = ApplicationResources()
    app.state.resources = resources

    assert get_app_resources(app) is resources


def test_get_health_service_returns_attached_service() -> None:
    app = FastAPI()
    service = HealthService(check_external_dependencies=False)
    app.state.health_service = service

    assert get_health_service(app) is service


def test_get_in_flight_tracker_returns_none_when_unset() -> None:
    app = FastAPI()
    app.state.in_flight_tracker = None

    assert get_in_flight_tracker(app) is None


def test_get_in_flight_tracker_returns_attached_tracker() -> None:
    app = FastAPI()
    tracker = InFlightTracker()
    app.state.in_flight_tracker = tracker

    assert get_in_flight_tracker(app) is tracker


def test_require_returns_value_when_present() -> None:
    sentinel = object()
    assert require(sentinel, code="x", message="y") is sentinel


def test_require_raises_service_unavailable_when_none() -> None:
    with pytest.raises(ServiceUnavailableError) as exc_info:
        require(
            None,
            code="cache_not_configured",
            message="Cache gateway is disabled or lifespan has not opened it",
        )

    assert exc_info.value.code == "cache_not_configured"
    assert "disabled or lifespan" in exc_info.value.message
