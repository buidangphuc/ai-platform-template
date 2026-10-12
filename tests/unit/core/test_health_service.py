import asyncio
import time

import pytest

from app.core.health import HealthChecks, HealthService


async def test_readiness_runs_all_registered_checks():
    calls: list[str] = []

    async def check_postgres() -> None:
        calls.append("postgres")

    async def check_redis() -> None:
        calls.append("redis")

    service = HealthService(
        check_external_dependencies=True,
        checks=(("postgres", check_postgres), ("redis", check_redis)),
    )

    result = await service.readiness()

    assert result.status == "ok"
    assert result.dependencies == {
        "api": "ok",
        "postgres": "ok",
        "redis": "ok",
    }
    assert calls == ["postgres", "redis"]


async def test_readiness_reports_down_dependencies():
    async def check_postgres() -> None:
        raise RuntimeError("database unavailable")

    async def check_redis() -> None:
        return None

    service = HealthService(
        check_external_dependencies=True,
        checks=(("postgres", check_postgres), ("redis", check_redis)),
    )

    result = await service.readiness()

    assert result.status == "error"
    assert result.dependencies == {
        "api": "ok",
        "postgres": "error",
        "redis": "ok",
    }


async def test_readiness_with_no_checks_returns_ok():
    service = HealthService(check_external_dependencies=True, checks=())

    result = await service.readiness()

    assert result.status == "ok"
    assert result.dependencies == {"api": "ok"}


async def test_readiness_skips_checks_when_external_dependencies_disabled():
    called = False

    async def should_not_run() -> None:
        nonlocal called
        called = True

    service = HealthService(
        check_external_dependencies=False,
        checks=(("postgres", should_not_run),),
    )

    result = await service.readiness()

    assert result.status == "ok"
    assert result.dependencies == {"api": "ok"}
    assert called is False


async def test_draining_service_reports_not_ready_without_running_checks():
    calls: list[str] = []

    async def check() -> None:
        calls.append("ran")

    service = HealthService(check_external_dependencies=True, checks=(("db", check),))
    service.begin_draining()

    result = await service.readiness()

    assert result.status == "draining"
    assert calls == []


async def test_checks_run_concurrently():
    async def slow() -> None:
        await asyncio.sleep(0.1)

    service = HealthService(checks=(("a", slow), ("b", slow), ("c", slow)))

    started = time.monotonic()
    result = await service.readiness()

    assert result.status == "ok"
    assert time.monotonic() - started < 0.25  # sequential would be >= 0.3


async def test_a_hung_check_times_out_without_blocking_the_others():
    async def hangs() -> None:
        await asyncio.sleep(30)

    async def fine() -> None:
        return None

    service = HealthService(
        checks=(("slow", hangs), ("fast", fine)), check_timeout_seconds=0.05
    )

    result = await service.readiness()

    assert result.status == "error"
    assert result.dependencies == {"api": "ok", "slow": "error", "fast": "ok"}


def test_registry_keeps_registration_order_and_rejects_duplicates():
    async def check() -> None:
        return None

    registry = HealthChecks(timeout_seconds=1.5)
    registry.register("postgres", check)
    registry.register("redis", check)

    assert [name for name, _ in registry.checks] == ["postgres", "redis"]
    assert registry.timeout_seconds == 1.5
    with pytest.raises(ValueError, match="postgres"):
        registry.register("postgres", check)
