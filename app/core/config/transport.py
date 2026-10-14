"""gRPC transport settings — the platform-contract server for team-ai."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TransportSettingsMixin(BaseModel):
    # gRPC server (implements the platform-core proto contract).
    GRPC_ENABLED: bool = False
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = Field(default=50051, gt=0)
    GRPC_REFLECTION_ENABLED: bool = True
    GRPC_GRACE_SECONDS: float = Field(default=10.0, ge=0)
