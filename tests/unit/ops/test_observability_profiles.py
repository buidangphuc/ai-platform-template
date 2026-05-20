from pathlib import Path


def test_debug_otel_collector_profile_is_present():
    profile = Path("ops/observability/otel-collector.debug.yaml")

    assert profile.exists()
    content = profile.read_text(encoding="utf-8")
    assert "receivers:" in content
    assert "otlp:" in content
    assert "exporters:" in content
    assert "debug:" in content
