from app.core.health import HealthService


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
