from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import get_app_resources
from app.core.config import Settings
from app.modules.platform.identity.auth import require_principal
from tests.factories import build_test_settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "DATABASE_ENABLED": True,
        "REDIS_ENABLED": True,
        "QUEUE_ENABLED": True,
        "QUEUE_BACKEND": "memory",
        "TASKS_ENABLED": True,
        "TASK_STORE_BACKEND": "memory",
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_BACKEND": "memory",
        "IDEMPOTENCY_ENABLED": True,
        "IDEMPOTENCY_BACKEND": "postgres",
        "CACHE_ENABLED": True,
        "CACHE_BACKEND": "memory",
        "WEBHOOKS_ENABLED": True,
        "WEBHOOK_SIGNING_SECRET": "test-webhook-secret",  # pragma: allowlist secret
        "OBJECTS_ENABLED": True,
        "OBJECT_BACKEND": "memory",
        "OUTBOX_ENABLED": True,
        "OUTBOX_BACKEND": "postgres",
        "GZIP_ENABLED": True,
        "REQUEST_TIMEOUT_ENABLED": True,
        "GRACEFUL_SHUTDOWN_ENABLED": True,
        "DOCS_ENABLED": True,
    }
    base.update(overrides)
    return build_test_settings(**base)


@dataclass
class _ExampleService:
    opened_at: datetime

    async def run(self, request: Request) -> dict[str, Any]:
        resources = get_app_resources(request.app)
        assert resources.cache is not None
        assert resources.objects is not None
        assert resources.queue_gateway is not None
        assert resources.task_service is not None
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

        task = await resources.task_service.submit(
            type="service-smoke",
            payload={"input": "ok"},
        )
        messages = await resources.queue_gateway.receive(
            max_messages=1, wait_seconds=0.01
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
                "example_service": hasattr(request.app.state, "example_service"),
            },
        }


class _ExampleServiceAddon:
    name = "example_service"

    def is_enabled(self, settings: Settings) -> bool:
        return True

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if not settings.DATABASE_ENABLED or not settings.TASKS_ENABLED:
            raise RuntimeError(
                "_ExampleServiceAddon requires DATABASE_ENABLED and TASKS_ENABLED"
            )
        app.state.example_service = _ExampleService(opened_at=datetime.now(UTC))

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        if hasattr(app.state, "example_service"):
            delattr(app.state, "example_service")


async def _service_smoke(request: Request) -> dict[str, Any]:
    return await request.app.state.example_service.run(request)


async def test_simple_service_app_runs_with_all_local_safe_feature_flags_enabled():
    app = create_app(
        settings=_settings(),
        init_resources=True,
        resource_addons=(_ExampleServiceAddon(),),
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
        assert resources_open.task_service is not None
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
    assert resources_closed.task_store is None
    assert resources_closed.cache is None
    assert resources_closed.objects is None
    assert resources_closed.addons == []
    assert not hasattr(app.state, "example_service")
