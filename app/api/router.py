from fastapi import APIRouter

from app.api.v1.health.router import router as health_router
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    return router
