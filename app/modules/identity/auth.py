import hmac

from fastapi import Header, Request

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_api_key
from app.modules.identity.repository import ApiKeyRepository
from app.modules.identity.schemas import AuthenticatedPrincipal


def validate_bootstrap_token(
    header_value: str | None,
    *,
    settings: Settings,
) -> None:
    if not settings.API_KEY_BOOTSTRAP_TOKEN:
        raise AppError(
            code="bootstrap_token_not_configured",
            message="API key creation is not configured",
            status_code=403,
        )
    if not header_value or not hmac.compare_digest(
        header_value,
        settings.API_KEY_BOOTSTRAP_TOKEN,
    ):
        raise AppError(
            code="forbidden", message="Invalid bootstrap token", status_code=403
        )


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


async def require_authenticated_request(request: Request) -> AuthenticatedPrincipal:
    principal = await authenticate_api_key(
        request.headers.get("Authorization"),
        settings=request.app.state.settings,
        repository=request.app.state.api_key_repository,
    )
    rate_limit = await request.app.state.rate_limiter.check(principal.api_key_id)
    if not rate_limit.allowed:
        raise AppError(
            code="rate_limit_exceeded",
            message="Rate limit exceeded",
            status_code=429,
        )
    return principal
