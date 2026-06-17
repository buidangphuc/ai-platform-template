from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

DependencyCheck = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class HealthResult:
    status: str
    dependencies: dict[str, str]


@dataclass
class HealthService:
    check_external_dependencies: bool = True
    checks: tuple[tuple[str, DependencyCheck], ...] = field(default_factory=tuple)

    async def readiness(self) -> HealthResult:
        dependencies = {"api": "ok"}
        if not self.check_external_dependencies:
            return HealthResult(status="ok", dependencies=dependencies)

        for name, check in self.checks:
            dependencies[name] = await self._run(check)

        status = "ok" if all(v == "ok" for v in dependencies.values()) else "error"
        return HealthResult(status=status, dependencies=dependencies)

    @staticmethod
    async def _run(check: DependencyCheck) -> str:
        try:
            await check()
        except Exception:
            return "error"
        return "ok"
