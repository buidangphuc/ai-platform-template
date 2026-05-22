from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.bootstrap.state import optional_app_resource
from app.core.health import HealthService

router = APIRouter(tags=["health"])


def _health_service(request: Request) -> HealthService:
    service = optional_app_resource(request.app, "health_service")
    if service is None:
        return HealthService(check_external_dependencies=False)
    return service


async def _liveness() -> dict[str, str]:
    return {"status": "ok"}


async def _readiness(request: Request) -> JSONResponse | dict[str, object]:
    result = await _health_service(request).readiness()
    payload = {
        "status": result.status,
        "dependencies": result.dependencies,
    }
    if result.status != "ok":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload
        )
    return payload


router.add_api_route("/healthz", _liveness, methods=["GET"], name="liveness")
router.add_api_route(
    "/readyz", _readiness, methods=["GET"], name="readiness", response_model=None
)
