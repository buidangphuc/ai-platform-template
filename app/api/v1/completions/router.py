from fastapi import APIRouter, Depends

from app.api.v1.completions import stream, sync, tasks
from app.modules.platform.identity.auth import require_principal

router = APIRouter()
router.include_router(
    sync.router,
    prefix="/completions",
    tags=["completions"],
    dependencies=[Depends(require_principal)],
)
router.include_router(
    stream.router,
    prefix="/completions",
    tags=["completions"],
    dependencies=[Depends(require_principal)],
)

# Mounted only when TASKS_ENABLED (see app/api/router.py).
tasks_router = APIRouter()
tasks_router.include_router(
    tasks.router,
    prefix="/completions",
    tags=["completions"],
    dependencies=[Depends(require_principal)],
)
