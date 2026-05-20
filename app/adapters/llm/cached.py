from app.contracts.llm import LLMClient, LLMRequest, LLMResponse
from app.contracts.llm_cache import LLMCacheKey, LLMResponseCache


class CachedLLMClient:
    def __init__(
        self,
        *,
        provider: str,
        client: LLMClient,
        cache: LLMResponseCache,
        enabled: bool = False,
        default_model: str | None = None,
    ) -> None:
        self.provider = provider
        self.client = client
        self.cache = cache
        self.enabled = enabled
        self.default_model = default_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.enabled or request.cache.bypass:
            return await self.client.complete(request)

        key = LLMCacheKey.from_request(
            provider=self.provider,
            request=request,
            default_model=self.default_model,
        )
        cache_hit = await self.cache.get(key)
        if cache_hit is not None:
            return cache_hit.response

        response = await self.client.complete(request)
        await self.cache.set(key, response)
        return response
