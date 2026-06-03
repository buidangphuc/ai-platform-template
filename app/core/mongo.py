"""Mongo client construction.

``motor`` is an optional dependency. It is imported lazily so the template can
run without Mongo support installed when ``MONGO_ENABLED=false``.
"""

from __future__ import annotations

import importlib
from typing import Any

from app.core.config import Settings


def build_mongo_client(settings: Settings) -> Any:
    try:
        motor_asyncio = importlib.import_module("motor.motor_asyncio")
    except ImportError as exc:
        raise RuntimeError(
            "motor is required when MONGO_ENABLED is true; install the 'mongo' extra"
        ) from exc
    client_cls = motor_asyncio.__dict__["AsyncIOMotorClient"]

    return client_cls(
        settings.MONGODB_URI,
        connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
        serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    )
