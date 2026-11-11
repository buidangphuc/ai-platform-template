from __future__ import annotations

from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import Depends, Request
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.application import create_app
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import get_app_resources
from app.core.config import Settings
from app.modules.platform.identity.auth import require_principal
from tests.infra import S3Target


def _settings(
    infra_settings: Callable[..., Settings], s3_target: S3Target, redis_prefix: str
) -> Settings:
    return infra_settings(
        DATABASE_ENABLED=True,
        REDIS_ENABLED=True,
        QUEUE_ENABLED=True,
        QUEUE_NAME=f"{redis_prefix}:queue",
        TASKS_ENABLED=True,
        TASK_STORE_BACKEND="postgres",
        TASK_REDIS_PREFIX=f"{redis_prefix}:tasks",
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_REDIS_PREFIX=f"{redis_prefix}:rate-limit",
        IDEMPOTENCY_ENABLED=True,
        IDEMPOTENCY_BACKEND="postgres",
        CACHE_ENABLED=True,
        CACHE_PREFIX=f"{redis_prefix}:cache",
        WEBHOOKS_ENABLED=True,
        WEBHOOK_SIGNING_SECRET="test-webhook-secret",  # pragma: allowlist secret
        OBJECTS_ENABLED=True,
        OBJECT_PREFIX=s3_target.prefix,
        OBJECT_S3_BUCKET=s3_target.bucket,
        OBJECT_S3_REGION=s3_target.region,
        OBJECT_S3_ENDPOINT_URL=s3_target.endpoint_url,
        OUTBOX_ENABLED=True,
        OUTBOX_BACKEND="postgres",
        GZIP_ENABLED=True,
        REQUEST_TIMEOUT_ENABLED=True,
        GRACEFUL_SHUTDOWN_ENABLED=True,
        DOCS_ENABLED=True,
    )


@dataclass
class _ExampleService:
    opened_at: datetime

    async def run(self, request: Request) -> dict[str, Any]:
        resources = get_app_resources(request.app)
        assert resources.cache is not None
        assert resources.objects is not None
        assert resources.queue_gateway is not None
        assert resources.tasks is not None
        assert resources.webhook_signer is not None

        await resources.cache.set("service-smoke/cache-key", b"cache-value")
        cached = await resources.cache.get("service-smoke/cache-key")

        await resources.objects.put(
            "service-smoke/object.txt",
            b"object-value",
            content_type="text/plain",
        )
        object_value = await resources.objects.get("service-smoke/object.txt")
        object_exists = await resources.objects.exists("service-smoke/object.txt")

        task = await resources.tasks.service.submit(
            type="service-smoke",
            payload={"input": "ok"},
            principal_id="smoke",
        )
        messages = await resources.queue_gateway.receive(
            max_messages=1, wait_seconds=1.0
        )
        if messages:
            await resources.queue_gateway.ack(messages[0])

        payload = b'{"service":"smoke"}'
        signature = resources.webhook_signer.sign(payload, timestamp=1_700_000_000)

        return {
            "cache": cached.decode("utf-8") if cached else None,
            "object": object_value.decode("utf-8") if object_value else None,
            "object_exists": object_exists,
            "task_status": task.status,
            "queue_messages": len(messages),
            "webhook_signature_verified": resources.webhook_signer.verify(
                payload,
                signature=signature,
                timestamp=1_700_000_000,
                now=1_700_000_000,
            ),
            "attached": {
                "idempotency_store": resources.idempotency_store is not None,
                "outbox_store": resources.outbox_store is not None,
                "example_service": _EXAMPLE_ADDON.service is not None,
            },
        }


class _ExampleServiceAddon:
    name = "example_service"
    service: _ExampleService | None = None

    def is_enabled(self, settings: Settings) -> bool:
        return True

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        if not settings.DATABASE_ENABLED or not settings.TASKS_ENABLED:
            raise RuntimeError(
                "_ExampleServiceAddon requires DATABASE_ENABLED and TASKS_ENABLED"
            )
        self.service = _ExampleService(opened_at=datetime.now(UTC))
        stack.callback(self._close)

    def _close(self) -> None:
        self.service = None


_EXAMPLE_ADDON = _ExampleServiceAddon()


async def _service_smoke(request: Request) -> dict[str, Any]:
    assert _EXAMPLE_ADDON.service is not None
    return await _EXAMPLE_ADDON.service.run(request)


async def test_simple_service_app_runs_with_every_capability_enabled(
    infra_settings: Callable[..., Settings],
    s3_target: S3Target,
    redis_client: Redis,
    redis_prefix: str,
    pg_sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_target.access_key)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_target.secret_key)
    app = create_app(
        settings=_settings(infra_settings, s3_target, redis_prefix),
        init_resources=True,
        resource_addons=(_EXAMPLE_ADDON,),
    )
    app.add_api_route(
        "/service-smoke",
        _service_smoke,
        methods=["POST"],
        dependencies=[Depends(require_principal)],
    )

    resources_before = app.state.resources
    assert resources_before.cache is None
    assert resources_before.objects is None

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.engine is not None
        assert resources_open.redis is not None
        assert resources_open.queue_gateway is not None
        assert resources_open.tasks is not None
        assert resources_open.cache is not None
        assert resources_open.objects is not None
        assert [addon.name for addon in resources_open.addons][-1] == "example_service"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/service-smoke",
                headers={"Authorization": "Bearer test-token"},
            )

        payload = response.json()

        assert response.status_code == 200
        assert payload["cache"] == "cache-value"
        assert payload["object"] == "object-value"
        assert payload["object_exists"] is True
        assert payload["task_status"] == "queued"
        assert payload["queue_messages"] == 1
        assert payload["webhook_signature_verified"] is True
        assert payload["attached"] == {
            "idempotency_store": True,
            "outbox_store": True,
            "example_service": True,
        }

    resources_closed = app.state.resources
    assert resources_closed.engine is None
    assert resources_closed.redis is None
    assert resources_closed.queue_gateway is None
    assert resources_closed.tasks is None
    assert resources_closed.cache is None
    assert resources_closed.objects is None
    assert resources_closed.addons == []
    assert _EXAMPLE_ADDON.service is None
