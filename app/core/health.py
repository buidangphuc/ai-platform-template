import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loguru import logger

DependencyCheck = Callable[[], Awaitable[None]]

DEFAULT_CHECK_TIMEOUT_SECONDS = 2.0


@dataclass
class HealthChecks:
    """Readiness checks registered by each opener as its resource comes up.

    Registration order is report order. ``timeout_seconds`` bounds every single
    check when ``HealthService`` runs them.
    """

    timeout_seconds: float = DEFAULT_CHECK_TIMEOUT_SECONDS
    _checks: dict[str, DependencyCheck] = field(default_factory=dict)

    def register(self, name: str, check: DependencyCheck) -> None:
        if name in self._checks:
            raise ValueError(f"health check {name!r} is already registered")
        self._checks[name] = check

    @property
    def checks(self) -> tuple[tuple[str, DependencyCheck], ...]:
        return tuple(self._checks.items())


@dataclass(frozen=True)
class HealthResult:
    status: str
    dependencies: dict[str, str]


@dataclass
class HealthService:
    check_external_dependencies: bool = True
    checks: tuple[tuple[str, DependencyCheck], ...] = field(default_factory=tuple)
    check_timeout_seconds: float = DEFAULT_CHECK_TIMEOUT_SECONDS
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

        outcomes = await asyncio.gather(
            *(self._run(name, check) for name, check in self.checks)
        )
        names = (name for name, _ in self.checks)
        dependencies.update(zip(names, outcomes, strict=True))

        status = "ok" if all(v == "ok" for v in dependencies.values()) else "error"
        return HealthResult(status=status, dependencies=dependencies)

    async def _run(self, name: str, check: DependencyCheck) -> str:
        try:
            async with asyncio.timeout(self.check_timeout_seconds):
                await check()
        except TimeoutError:
            logger.warning(
                "health check {} timed out after {}s",
                name,
                self.check_timeout_seconds,
            )
            return "error"
        except Exception:
            return "error"
        return "ok"
