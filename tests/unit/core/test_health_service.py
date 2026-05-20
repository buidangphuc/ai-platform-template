from app.core.health import HealthService


async def test_readiness_checks_postgres_and_redis_when_enabled():
    calls: list[str] = []

    async def check_postgres() -> None:
        calls.append("postgres")

    async def check_redis() -> None:
        calls.append("redis")

    service = HealthService(
        check_external_dependencies=True,
        postgres_check=check_postgres,
        redis_check=check_redis,
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
        postgres_check=check_postgres,
        redis_check=check_redis,
    )

    result = await service.readiness()

    assert result.status == "error"
    assert result.dependencies == {
        "api": "ok",
        "postgres": "error",
        "redis": "ok",
    }
