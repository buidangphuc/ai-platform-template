import hashlib
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.modules.platform.http.upstream import UpstreamClient


def sha256_hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def api_key_entry(subject: str, token: str, *scopes: str) -> str:
    """One ``AUTH_API_KEYS`` entry: ``subject:scope|scope:sha256hex``."""
    return f"{subject}:{'|'.join(scopes)}:{sha256_hex(token)}"


def build_test_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": 6379,
        "REDIS_PASSWORD": "",  # pragma: allowlist secret
        "REDIS_DATABASE": 0,
        "AUTH_API_KEYS": api_key_entry("test-user", "test-token", "admin", "developer"),
    }
    values.update(overrides)
    return Settings(**values)


@asynccontextmanager
async def api_client_for(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Client for an app with its lifespan running, as in production."""
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client


async def open_addon(addon, resources, settings: Settings) -> AsyncExitStack:
    """Open one addon outside the app; ``await stack.aclose()`` closes it."""
    stack = AsyncExitStack()
    await addon.open(resources, settings, stack)
    return stack


def local_upstreams(monkeypatch, urls: Mapping[str, str]):
    """Point the named upstreams at local base URLs; others keep their own."""
    original = UpstreamClient.from_upstream.__func__

    def from_upstream(cls, upstream, settings):
        if upstream.name in urls:
            upstream = replace(upstream, base_url=lambda _settings: urls[upstream.name])
        return original(cls, upstream, settings)

    monkeypatch.setattr(UpstreamClient, "from_upstream", classmethod(from_upstream))
