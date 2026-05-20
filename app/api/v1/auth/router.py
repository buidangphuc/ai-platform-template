from fastapi import APIRouter, Header, Request, Response, status

from app.core.security import create_api_key, hash_api_key
from app.modules.identity.auth import authenticate_api_key, validate_bootstrap_token
from app.modules.identity.repository import ApiKeyRepository
from app.modules.identity.schemas import (
    AuthenticatedPrincipal,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _repository(request: Request) -> ApiKeyRepository:
    return request.app.state.api_key_repository


@router.post(
    "/api-keys",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_key(
    payload: CreateApiKeyRequest,
    request: Request,
    response: Response,
    bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
):
    settings = request.app.state.settings
    validate_bootstrap_token(bootstrap_token, settings=settings)
    raw_key = create_api_key()
    key_hash = hash_api_key(raw_key, pepper=settings.API_KEY_PEPPER)
    api_key = await _repository(request).create(name=payload.name, key_hash=key_hash)
    response.headers["Cache-Control"] = "no-store"
    return CreateApiKeyResponse(
        api_key_id=api_key.id,
        name=api_key.name,
        api_key=raw_key,
    )


@router.get("/me", response_model=AuthenticatedPrincipal)
async def me(request: Request):
    principal = await authenticate_api_key(
        request.headers.get("Authorization"),
        settings=request.app.state.settings,
        repository=_repository(request),
    )
    return principal
