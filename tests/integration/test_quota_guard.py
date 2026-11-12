from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.modules.platform.identity.auth import require_principal
from app.modules.platform.quota.http import require_quota
from app.modules.platform.quota.models import QuotaPolicy
from tests.factories import api_client_for

HEADERS = {"Authorization": "Bearer test-token"}
POLICY = QuotaPolicy("limited", limit=1, window_seconds=3600)


def _guarded_app(settings: Settings, calls: list[str]):
    app = create_app(settings=settings, init_resources=True)

    async def limited() -> dict[str, str]:
        calls.append("limited")
        return {"ok": "yes"}

    app.add_api_route(
        "/limited",
        limited,
        methods=["POST"],
        dependencies=[Depends(require_principal), Depends(require_quota(POLICY))],
    )
    return app


async def test_guard_works_with_the_shipped_addon(
    infra_settings: Callable[..., Settings],
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    calls: list[str] = []
    app = _guarded_app(infra_settings(DATABASE_ENABLED=True, QUOTA_ENABLED=True), calls)

    async with api_client_for(app) as client:
        first = await client.post("/limited", headers=HEADERS)
        second = await client.post("/limited", headers=HEADERS)

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1
    assert calls == ["limited"]


async def test_guard_reports_unavailable_when_quota_is_disabled(
    infra_settings: Callable[..., Settings],
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    calls: list[str] = []
    app = _guarded_app(infra_settings(DATABASE_ENABLED=True), calls)

    async with api_client_for(app) as client:
        response = await client.post("/limited", headers=HEADERS)

    assert response.status_code == 503
    assert calls == []
