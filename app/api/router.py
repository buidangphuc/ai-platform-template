from fastapi import APIRouter

from app.api.v1.acompletions.router import router as acompletions_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.completions.router import router as completions_router
from app.api.v1.completions.stream import router as completions_stream_router
from app.api.v1.health.router import router as health_router
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(health_router, prefix=settings.API_V1_PREFIX)
    router.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    router.include_router(completions_router, prefix=settings.API_V1_PREFIX)
    router.include_router(completions_stream_router, prefix=settings.API_V1_PREFIX)
    router.include_router(acompletions_router, prefix=settings.API_V1_PREFIX)
    return router
