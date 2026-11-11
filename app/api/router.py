from fastapi import APIRouter

from app.api.v1.health.router import router as health_router
from app.bootstrap.features.base import Feature
from app.core.config import Settings


def build_api_router(settings: Settings, features: tuple[Feature, ...]) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(health_router, prefix=settings.API_V1_PREFIX)
    for feature in features:
        if not feature.enabled(settings):
            continue
        for feature_router in feature.routers:
            router.include_router(feature_router, prefix=settings.API_V1_PREFIX)
        if settings.TASKS_ENABLED:
            for task_router in feature.task_routers:
                router.include_router(task_router, prefix=settings.API_V1_PREFIX)
    return router
