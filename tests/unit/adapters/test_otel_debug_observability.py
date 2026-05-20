import logging

from app.adapters.observability.otel_debug import OTelDebugObservability


async def test_otel_debug_observability_emits_span_logs(caplog):
    observability = OTelDebugObservability(endpoint="http://collector:4318")

    with caplog.at_level(logging.INFO, logger="otel.debug"):
        async with observability.start_span(
            "rag.answer",
            attributes={"ai.operation": "rag.answer"},
        ) as span:
            span.set_attribute("ai.model", "fake-chat")

    assert observability.finished_spans[0].name == "rag.answer"
    assert "otel.trace" in caplog.text
    assert "http://collector:4318" in caplog.text
