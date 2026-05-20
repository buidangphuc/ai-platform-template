from dataclasses import dataclass


@dataclass(frozen=True)
class HealthResult:
    status: str
    dependencies: dict[str, str]


class HealthService:
    def __init__(self, check_external_dependencies: bool = True) -> None:
        self.check_external_dependencies = check_external_dependencies

    async def health(self) -> HealthResult:
        return HealthResult(status="ok", dependencies={"api": "ok"})

    async def readiness(self) -> HealthResult:
        dependencies = {"api": "ok"}
        return HealthResult(status="ok", dependencies=dependencies)
