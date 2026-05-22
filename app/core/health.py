from collections.abc import Awaitable, Callable
from dataclasses import dataclass

DependencyCheck = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class HealthResult:
    status: str
    dependencies: dict[str, str]


class HealthService:
    def __init__(
        self,
        check_external_dependencies: bool = True,
        *,
        postgres_check: DependencyCheck | None = None,
        redis_check: DependencyCheck | None = None,
    ) -> None:
        self.check_external_dependencies = check_external_dependencies
        self.postgres_check = postgres_check
        self.redis_check = redis_check

    async def readiness(self) -> HealthResult:
        dependencies = {"api": "ok"}
        if not self.check_external_dependencies:
            return HealthResult(status="ok", dependencies=dependencies)

        checks = {
            name: check
            for name, check in {
                "postgres": self.postgres_check,
                "redis": self.redis_check,
            }.items()
            if check is not None
        }
        for name, check in checks.items():
            dependencies[name] = await self._check_dependency(check)

        status = (
            "ok" if all(value == "ok" for value in dependencies.values()) else "error"
        )
        return HealthResult(status=status, dependencies=dependencies)

    async def _check_dependency(self, check: DependencyCheck | None) -> str:
        if check is None:
            return "not_configured"
        try:
            await check()
        except Exception:
            return "error"
        return "ok"
