"""Thin async wrapper over a Motor client scoped to one database."""

from __future__ import annotations

from typing import Any


class MongoGateway:
    def __init__(self, client: Any, *, database: str) -> None:
        self._client = client
        self._database_name = database

    @property
    def client(self) -> Any:
        return self._client

    @property
    def database(self) -> Any:
        return self._client[self._database_name]

    def collection(self, name: str) -> Any:
        return self.database[name]

    async def ping(self) -> Any:
        return await self._client.admin.command("ping")

    async def close(self) -> None:
        # Motor's AsyncIOMotorClient.close() is synchronous.
        self._client.close()
