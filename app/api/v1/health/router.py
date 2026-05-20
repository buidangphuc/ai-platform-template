from fastapi import APIRouter, Request

from app.core.health import HealthService

router = APIRouter(tags=["health"])


def _health_service(request: Request) -> HealthService:
    return request.app.state.health_service


@router.get("/health")
async def health(request: Request):
    result = await _health_service(request).health()
    return {"status": result.status}


@router.get("/ready")
async def readiness(request: Request):
    result = await _health_service(request).readiness()
    return {
        "status": result.status,
        "dependencies": result.dependencies,
    }
