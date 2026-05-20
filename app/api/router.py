from fastapi import APIRouter

from app.api.v1.agents.router import router as agents_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.evals.router import router as evals_router
from app.api.v1.feedback.router import router as feedback_router
from app.api.v1.health.router import router as health_router
from app.api.v1.rag.router import router as rag_router
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(health_router, prefix=settings.API_V1_PREFIX)
    router.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    router.include_router(feedback_router, prefix=settings.API_V1_PREFIX)
    router.include_router(rag_router, prefix=settings.API_V1_PREFIX)
    router.include_router(evals_router, prefix=settings.API_V1_PREFIX)
    router.include_router(agents_router, prefix=settings.API_V1_PREFIX)
    return router
