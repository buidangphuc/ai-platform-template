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
    draining: bool = False

    def begin_draining(self) -> None:
        """Report not-ready from now on; set once shutdown starts, never cleared."""
        self.draining = True

    async def readiness(self) -> HealthResult:
        if self.draining:
            return HealthResult(status="draining", dependencies={"api": "draining"})
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
