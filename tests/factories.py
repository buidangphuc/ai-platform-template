import hashlib
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings


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
