from app.modules.usage.schemas import UsageRecord
from app.modules.usage.tracker import InMemoryUsageTracker


async def test_usage_tracker_records_llm_usage():
    tracker = InMemoryUsageTracker()
    record = UsageRecord(
        operation="llm.complete",
        provider="fake",
        model="fake-chat",
        input_tokens=5,
        output_tokens=3,
        latency_ms=12.5,
        estimated_cost=0.0,
        metadata={"request_id": "req-1"},
    )

    stored = await tracker.record(record)

    assert stored.id
    assert stored.total_tokens == 8
    assert tracker.records == [stored]
