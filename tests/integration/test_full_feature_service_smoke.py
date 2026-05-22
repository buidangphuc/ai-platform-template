from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.identity.auth import require_principal


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
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
    return Settings(**base)


@dataclass
class _ExampleService:
    opened_at: datetime

    async def run(self, request: Request) -> dict[str, Any]:
        cache = request.app.state.cache
        objects = request.app.state.objects
        queue = request.app.state.queue_gateway
        task_service = request.app.state.task_service
        signer = request.app.state.webhook_signer
        manifest = request.app.state.bootstrap_manifest

        await cache.set("service-smoke/cache-key", b"cache-value")
        cached = await cache.get("service-smoke/cache-key")

        await objects.put(
            "service-smoke/object.txt",
            b"object-value",
            content_type="text/plain",
        )
        object_value = await objects.get("service-smoke/object.txt")
        object_exists = await objects.exists("service-smoke/object.txt")

        task = await task_service.submit(
            type="service-smoke",
            payload={"input": "ok"},
        )
        messages = await queue.receive(max_messages=1, wait_seconds=0.01)
        if messages:
            await queue.ack(messages[0])

        payload = b'{"service":"smoke"}'
        signature = signer.sign(payload, timestamp=1_700_000_000)

        return {
            "cache": cached.decode("utf-8") if cached else None,
            "object": object_value.decode("utf-8") if object_value else None,
            "object_exists": object_exists,
            "task_status": task.status,
            "queue_messages": len(messages),
            "webhook_signature_verified": signer.verify(
                payload,
                signature=signature,
                timestamp=1_700_000_000,
                now=1_700_000_000,
            ),
            "manifest": manifest.to_dict(),
            "attached": {
                "idempotency_store": hasattr(request.app.state, "idempotency_store"),
                "outbox_store": hasattr(request.app.state, "outbox_store"),
                "example_service": hasattr(request.app.state, "example_service"),
            },
        }


class _ExampleServiceAddon:
    name = "example_service"

    def is_enabled(self, settings: Settings) -> bool:
        return True

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ("database", "redis", "queue", "tasks")

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
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

    assert app.state.bootstrap_manifest.resources["database"].status == "planned"
    assert app.state.bootstrap_manifest.resources["redis"].status == "planned"
    assert app.state.bootstrap_manifest.resources["queue"].status == "planned"
    assert app.state.bootstrap_manifest.resources["tasks"].status == "planned"

    async with app.router.lifespan_context(app):
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
        assert payload["manifest"]["resources"]["database"]["status"] == "opened"
        assert payload["manifest"]["resources"]["redis"]["status"] == "opened"
        assert payload["manifest"]["resources"]["queue"]["status"] == "opened"
        assert payload["manifest"]["resources"]["tasks"]["status"] == "opened"
        assert payload["manifest"]["addons"][-1]["name"] == "example_service"
        assert payload["manifest"]["addons"][-1]["status"] == "opened"

    assert app.state.bootstrap_manifest.resources["database"].status == "closed"
    assert app.state.bootstrap_manifest.resources["redis"].status == "closed"
    assert app.state.bootstrap_manifest.resources["queue"].status == "closed"
    assert app.state.bootstrap_manifest.resources["tasks"].status == "closed"
    assert not hasattr(app.state, "cache")
    assert not hasattr(app.state, "objects")
    assert not hasattr(app.state, "example_service")
