import hmac

from fastapi import Request
from fastapi.security.utils import get_authorization_scheme_param

from app.bootstrap.state import get_app_settings, optional_app_resource
from app.core.config import Settings
from app.core.errors import ForbiddenError, RateLimitError, UnauthorizedError
from app.modules.identity.schemas import Principal


async def authenticate_bearer_token(
    authorization: str | None,
    *,
    settings: Settings,
) -> Principal:
    if not settings.AUTH_BEARER_TOKEN:
        raise ForbiddenError(
            "Bearer token authentication is not configured",
            code="auth_not_configured",
        )

    scheme, token = get_authorization_scheme_param(authorization)
    if not authorization or scheme.lower() != "bearer":
        raise UnauthorizedError("Missing bearer token")

    if not hmac.compare_digest(token, settings.AUTH_BEARER_TOKEN):
        raise UnauthorizedError("Invalid bearer token")

    return Principal(
        id=settings.AUTH_SUBJECT,
        type="service",
        scopes=tuple(settings.auth_roles),
    )


async def _enforce_rate_limit(request: Request, principal: Principal) -> None:
    rate_limiter = optional_app_resource(request.app, "rate_limiter")
    if rate_limiter is None:
        return
    rate_limit = await rate_limiter.check(principal.id)
    if not rate_limit.allowed:
        raise RateLimitError()


async def require_principal(request: Request) -> Principal:
    principal = await authenticate_bearer_token(
        request.headers.get("Authorization"),
        settings=get_app_settings(request.app),
    )
    request.state.principal = principal
    await _enforce_rate_limit(request, principal)
    return principal
