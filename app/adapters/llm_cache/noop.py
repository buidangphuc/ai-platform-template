from app.contracts.llm import LLMResponse
from app.contracts.llm_cache import LLMCacheHit, LLMCacheKey


class NoOpLLMResponseCache:
    async def get(self, key: LLMCacheKey) -> LLMCacheHit | None:
        return None

    async def set(
        self,
        key: LLMCacheKey,
        response: LLMResponse,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        return None
