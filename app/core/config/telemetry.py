"""OpenTelemetry settings.

Off by default. When ``OTEL_ENABLED`` the app exports traces and GenAI metrics
over OTLP/HTTP to ``OTEL_EXPORTER_OTLP_ENDPOINT`` (needs the ``otel`` extra).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TelemetrySettingsMixin(BaseModel):
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = Field(default="ai-platform", min_length=1)
    # Base OTLP/HTTP endpoint, e.g. http://localhost:4318 (no /v1/traces suffix).
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_TRACES_SAMPLE_RATIO: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _require_endpoint_when_enabled(self) -> TelemetrySettingsMixin:
        if self.OTEL_ENABLED and not self.OTEL_EXPORTER_OTLP_ENDPOINT:
            raise ValueError(
                "OTEL_EXPORTER_OTLP_ENDPOINT is required when OTEL_ENABLED is true"
            )
        return self
