import hashlib
import hmac
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, Request
from fastapi.security.utils import get_authorization_scheme_param

from app.bootstrap.state import get_app_resources, get_app_settings
from app.core.config import Settings
from app.core.config.platform import ApiKey
from app.core.errors import ForbiddenError, RateLimitError, UnauthorizedError
from app.modules.platform.identity.schemas import Principal


async def authenticate_bearer_token(
    authorization: str | None,
    *,
    settings: Settings,
) -> Principal:
    keys = settings.auth_api_keys
    if not keys:
        raise ForbiddenError(
            "API key authentication is not configured",
            code="auth_not_configured",
        )

    scheme, token = get_authorization_scheme_param(authorization)
    if not authorization or scheme.lower() != "bearer":
        raise UnauthorizedError("Missing bearer token")

    presented = hashlib.sha256(token.encode()).digest()
    # Compare against every key (no early exit) so timing does not reveal which
    # key, or how many, matched.
    matched: ApiKey | None = None
    for key in keys:
        if hmac.compare_digest(presented, key.digest):
            matched = key
    if matched is None:
        raise UnauthorizedError("Invalid bearer token")

    return Principal(id=matched.subject, type="service", scopes=matched.scopes)


async def _enforce_rate_limit(request: Request, principal: Principal) -> None:
    rate_limiter = get_app_resources(request.app).principal_rate_limiter
    if rate_limiter is None:
        return
    result = await rate_limiter.check(principal.id)
    if not result.allowed:
        raise RateLimitError(retry_after_seconds=result.retry_after_seconds)


async def require_principal(request: Request) -> Principal:
    principal = await authenticate_bearer_token(
        request.headers.get("Authorization"),
        settings=get_app_settings(request.app),
    )
    request.state.principal = principal
    await _enforce_rate_limit(request, principal)
    return principal


def require_scopes(
    *required: str,
) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    """Build a dependency that enforces ``principal.scopes`` ⊇ ``required``.

    Usage::

        @router.post(
            "/admin/users",
            dependencies=[Depends(require_scopes("admin"))],
        )
        async def create_user(...): ...
    """
    required_set = frozenset(required)

    async def dependency(
        principal: Principal = Depends(require_principal),
    ) -> Principal:
        missing = sorted(required_set - set(principal.scopes))
        if missing:
            raise ForbiddenError(
                f"Missing required scopes: {missing}",
                code="insufficient_scope",
                data={"required": sorted(required_set), "missing": missing},
            )
        return principal

    return dependency
