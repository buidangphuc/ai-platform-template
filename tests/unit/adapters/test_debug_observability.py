from app.adapters.observability.debug import DebugObservability
from app.contracts.observability import ObservabilityClient


async def test_debug_observability_records_spans_and_events():
    observability: ObservabilityClient = DebugObservability()

    async with observability.start_span(
        "llm.complete",
        attributes={"provider": "fake"},
    ) as span:
        span.set_attribute("model", "fake-chat")
        await observability.record_event(
            "llm.usage",
            attributes={"input_tokens": 3, "output_tokens": 2},
        )

    assert len(observability.finished_spans) == 1
    assert observability.finished_spans[0].name == "llm.complete"
    assert observability.finished_spans[0].attributes == {
        "provider": "fake",
        "model": "fake-chat",
    }
    assert observability.events[0].name == "llm.usage"
    assert observability.events[0].attributes == {
        "input_tokens": 3,
        "output_tokens": 2,
    }
