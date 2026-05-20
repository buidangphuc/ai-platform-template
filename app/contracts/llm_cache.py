import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.contracts.llm import LLMRequest, LLMResponse


@dataclass(frozen=True)
class LLMCacheKey:
    provider: str
    model: str
    prompt_version: str | None
    tenant_id: str | None
    user_id: str | None
    cache_scope: str | None
    request_hash: str

    @classmethod
    def from_request(
        cls,
        *,
        provider: str,
        request: LLMRequest,
        default_model: str | None = None,
    ) -> "LLMCacheKey":
        model = request.model or default_model or ""
        payload = request.model_dump(
            mode="json",
            exclude={"metadata": True, "cache": {"bypass"}},
        )
        payload["model"] = model
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return cls(
            provider=provider,
            model=model,
            prompt_version=request.prompt_version,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            cache_scope=request.cache.scope,
            request_hash=hashlib.sha256(encoded).hexdigest(),
        )


class LLMCacheHit(BaseModel):
    response: LLMResponse
    metadata: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class LLMResponseCache(Protocol):
    async def get(self, key: LLMCacheKey) -> LLMCacheHit | None:
        raise NotImplementedError

    async def set(
        self,
        key: LLMCacheKey,
        response: LLMResponse,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        raise NotImplementedError
