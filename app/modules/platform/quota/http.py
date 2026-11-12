"""Optional route guard: reserve quota before the handler runs.

Opt-in example: no route in this template enables it. Set ``QUOTA_ENABLED=true``,
then add the dependency with the policy that governs the route::

    REPORTS = QuotaPolicy("reports", limit=100, window_seconds=3600)

    @router.post("/reports", dependencies=[Depends(require_quota(REPORTS))])
    async def create_report(...): ...

Exceeding the policy raises ``RateLimitError`` (429 with ``Retry-After``).
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request

from app.bootstrap.state import get_quota_service
from app.modules.platform.identity.auth import require_principal
from app.modules.platform.identity.schemas import Principal
from app.modules.platform.quota.models import QuotaPolicy


def require_quota(policy: QuotaPolicy, cost: int = 1) -> Callable[..., Awaitable[None]]:
    async def dependency(
        request: Request, principal: Principal = Depends(require_principal)
    ) -> None:
        await get_quota_service(request.app).reserve(
            subject_id=principal.id, policy=policy, cost=cost
        )

    return dependency
