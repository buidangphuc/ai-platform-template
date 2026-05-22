from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap.state import get_app_settings
from app.core.database import DbSession
from app.core.idempotency import get_idempotency_key
from app.core.request_context import get_request_id
from app.modules.identity.auth import require_principal
from app.modules.identity.schemas import Principal


@dataclass(frozen=True, slots=True)
class ServiceContext:
    request_id: str
    principal: Principal
    idempotency_key: str | None
    db: AsyncSession


def build_service_context(
    *,
    request: Request,
    request_id: str,
    principal: Principal,
    db: AsyncSession,
    idempotency_enabled: bool,
) -> ServiceContext:
    return ServiceContext(
        request_id=request_id,
        principal=principal,
        idempotency_key=(get_idempotency_key(request) if idempotency_enabled else None),
        db=db,
    )


async def get_service_context(
    request: Request,
    db: DbSession,
    principal: Principal = Depends(require_principal),
) -> ServiceContext:
    return build_service_context(
        request=request,
        request_id=get_request_id(),
        principal=principal,
        db=db,
        idempotency_enabled=get_app_settings(request.app).IDEMPOTENCY_ENABLED,
    )


ServiceContextDep = Annotated[ServiceContext, Depends(get_service_context)]
