from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.health import HealthService

router = APIRouter(tags=["health"])


def _health_service(request: Request) -> HealthService:
    return request.app.state.health_service


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
