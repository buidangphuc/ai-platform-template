from fastapi import Header

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_api_key
from app.modules.identity.repository import ApiKeyRepository
from app.modules.identity.schemas import AuthenticatedPrincipal


async def authenticate_api_key(
    authorization: str | None,
    *,
    settings: Settings,
    repository: ApiKeyRepository,
) -> AuthenticatedPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(code="unauthorized", message="Missing API key", status_code=401)

    raw_api_key = authorization.removeprefix("Bearer ").strip()
    key_hash = hash_api_key(raw_api_key, pepper=settings.API_KEY_PEPPER)
    api_key = await repository.get_active_by_hash(key_hash)
    if api_key is None:
        raise AppError(code="unauthorized", message="Invalid API key", status_code=401)

    return AuthenticatedPrincipal(
        auth_type="api_key",
        api_key_id=api_key.id,
        name=api_key.name,
    )


def authorization_header(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str | None:
    return authorization
