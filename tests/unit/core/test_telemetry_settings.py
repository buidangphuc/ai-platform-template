import pytest
from pydantic import ValidationError

from app.bootstrap.addons.base import default_resource_addons
from app.bootstrap.addons.telemetry import TelemetryAddon
from app.bootstrap.resources import ApplicationResources, open_application_resources
from tests.factories import build_test_settings, open_addon


def test_telemetry_is_off_by_default_and_needs_no_endpoint():
    settings = build_test_settings()

    assert settings.OTEL_ENABLED is False
    assert settings.OTEL_EXPORTER_OTLP_ENDPOINT == ""
    assert TelemetryAddon().is_enabled(settings) is False


def test_enabling_telemetry_requires_an_endpoint():
    with pytest.raises(ValidationError, match="OTEL_EXPORTER_OTLP_ENDPOINT"):
        build_test_settings(OTEL_ENABLED=True)


@pytest.mark.parametrize("ratio", [-0.1, 1.1])
def test_sample_ratio_is_bounded(ratio: float):
    with pytest.raises(ValidationError):
        build_test_settings(OTEL_TRACES_SAMPLE_RATIO=ratio)


async def test_telemetry_off_creates_no_provider(monkeypatch: pytest.MonkeyPatch):
    telemetry_module = pytest.importorskip("app.core.telemetry_otel")

    def fail(settings):
        raise AssertionError("providers must not be built when telemetry is off")

    monkeypatch.setattr(telemetry_module, "build_telemetry", fail)

    async with open_application_resources(
        build_test_settings(),
        init_resources=False,
        addons=default_resource_addons(),
    ) as resources:
        assert resources.telemetry is None


async def test_addon_builds_the_handle_and_shuts_it_down_on_close():
    pytest.importorskip("opentelemetry.sdk")
    settings = build_test_settings(
        OTEL_ENABLED=True, OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:1"
    )
    resources = ApplicationResources()

    stack = await open_addon(TelemetryAddon(), resources, settings)

    assert resources.telemetry is not None
    await stack.aclose()
