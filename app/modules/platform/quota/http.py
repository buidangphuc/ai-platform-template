"""Optional route guard: reserve quota before the handler runs.

Opt-in example: no route in this template enables it. Configure a policy for the
resource on the quota service (``QUOTA_ENABLED=true``), then add the dependency::

    @router.post("/reports", dependencies=[Depends(require_quota("reports"))])
    async def create_report(...): ...

Exceeding the policy raises ``RateLimitError`` (429 with ``Retry-After``).
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request

from app.bootstrap.state import get_quota_service
from app.modules.platform.identity.auth import require_principal
from app.modules.platform.identity.schemas import Principal


def require_quota(resource: str, cost: int = 1) -> Callable[..., Awaitable[None]]:
    async def dependency(
        request: Request, principal: Principal = Depends(require_principal)
    ) -> None:
        await get_quota_service(request.app).reserve(
            subject_id=principal.id, resource=resource, cost=cost
        )

    return dependency
