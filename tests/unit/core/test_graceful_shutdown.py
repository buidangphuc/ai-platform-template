import asyncio

import pytest

from app.core.middleware import InFlightTracker


async def test_tracker_starts_idle():
    tracker = InFlightTracker()
    assert tracker.count == 0
    assert await tracker.wait_idle(timeout=0.05) is True


async def test_tracker_acquire_release_round_trip():
    tracker = InFlightTracker()
    tracker.acquire()
    tracker.acquire()
    assert tracker.count == 2
    tracker.release()
    tracker.release()
    assert tracker.count == 0
    assert await tracker.wait_idle(timeout=0.05) is True


async def test_wait_idle_returns_false_when_requests_outlive_timeout():
    tracker = InFlightTracker()
    tracker.acquire()

    drained = await tracker.wait_idle(timeout=0.05)

    assert drained is False
    assert tracker.count == 1


async def test_wait_idle_succeeds_after_concurrent_release():
    tracker = InFlightTracker()
    tracker.acquire()

    async def release_after_delay() -> None:
        await asyncio.sleep(0.05)
        tracker.release()

    release_task = asyncio.create_task(release_after_delay())
    try:
        drained = await tracker.wait_idle(timeout=1.0)
    finally:
        await release_task

    assert drained is True
    assert tracker.count == 0


async def test_release_below_zero_is_clamped():
    tracker = InFlightTracker()
    tracker.release()
    tracker.release()
    assert tracker.count == 0
    assert await tracker.wait_idle(timeout=0.01) is True


@pytest.mark.parametrize("count", [1, 5, 20])
async def test_tracker_handles_many_concurrent_requests(count: int):
    tracker = InFlightTracker()
    for _ in range(count):
        tracker.acquire()
    assert tracker.count == count

    for _ in range(count):
        tracker.release()
    assert tracker.count == 0
