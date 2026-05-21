from fastapi import APIRouter, Depends, Response

from app.modules.identity.auth import require_principal
from app.modules.identity.schemas import Principal

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=Principal)
async def me(
    response: Response,
    principal: Principal = Depends(require_principal),
):
    response.headers["Cache-Control"] = "no-store"
    return principal
