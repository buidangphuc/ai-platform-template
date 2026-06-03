"""MongoDB runtime settings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MongoSettingsMixin(BaseModel):
    MONGO_ENABLED: bool = False
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "app"
    MONGODB_CONNECT_TIMEOUT_MS: int = Field(default=10_000, gt=0)
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = Field(default=10_000, gt=0)
