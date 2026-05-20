from app.adapters.llm.cached import CachedLLMClient
from app.adapters.llm_cache.noop import NoOpLLMResponseCache
from app.contracts.llm import (
    ChatMessage,
    LLMCacheOptions,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from app.contracts.llm_cache import LLMCacheHit, LLMCacheKey, LLMResponseCache


class CountingLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content=f"call-{self.calls}",
            model=request.model or "fake-chat",
            finish_reason="stop",
            usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class MemoryLLMResponseCache:
    def __init__(self) -> None:
        self.values: dict[LLMCacheKey, LLMCacheHit] = {}

    async def get(self, key: LLMCacheKey) -> LLMCacheHit | None:
        return self.values.get(key)

    async def set(
        self,
        key: LLMCacheKey,
        response: LLMResponse,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.values[key] = LLMCacheHit(response=response, metadata=metadata or {})


async def test_noop_llm_cache_never_returns_cached_responses():
    cache: LLMResponseCache = NoOpLLMResponseCache()
    request = LLMRequest(
        messages=[ChatMessage(role="user", content="hello")],
        model="fake-chat",
    )
    response = LLMResponse(
        content="cached",
        model="fake-chat",
        finish_reason="stop",
        usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
    )
    key = LLMCacheKey.from_request(provider="fake", request=request)

    await cache.set(key, response)

    assert await cache.get(key) is None


async def test_cached_llm_client_uses_cache_for_repeated_requests():
    llm = CountingLLMClient()
    cached = CachedLLMClient(
        provider="fake",
        client=llm,
        cache=MemoryLLMResponseCache(),
        enabled=True,
    )
    request = LLMRequest(
        messages=[ChatMessage(role="user", content="hello")],
        model="fake-chat",
    )

    first = await cached.complete(request)
    second = await cached.complete(request)

    assert first.content == "call-1"
    assert second.content == "call-1"
    assert llm.calls == 1


async def test_cached_llm_client_can_be_disabled_by_configuration():
    llm = CountingLLMClient()
    cached = CachedLLMClient(
        provider="fake",
        client=llm,
        cache=MemoryLLMResponseCache(),
        enabled=False,
    )
    request = LLMRequest(
        messages=[ChatMessage(role="user", content="hello")],
        model="fake-chat",
    )

    first = await cached.complete(request)
    second = await cached.complete(request)

    assert first.content == "call-1"
    assert second.content == "call-2"
    assert llm.calls == 2


async def test_cached_llm_client_honors_per_request_bypass():
    llm = CountingLLMClient()
    cached = CachedLLMClient(
        provider="fake",
        client=llm,
        cache=MemoryLLMResponseCache(),
        enabled=True,
    )
    request = LLMRequest(
        messages=[ChatMessage(role="user", content="hello")],
        model="fake-chat",
        cache=LLMCacheOptions(bypass=True),
    )

    first = await cached.complete(request)
    second = await cached.complete(request)

    assert first.content == "call-1"
    assert second.content == "call-2"
    assert llm.calls == 2


def test_llm_cache_key_includes_scope_prompt_tools_generation_and_safety_fields():
    base_request = LLMRequest(
        messages=[ChatMessage(role="user", content="hello")],
        model="fake-chat",
        temperature=0.2,
        prompt_version="rag-answer:v1",
        tools=[{"name": "search"}],
        tenant_id="tenant-a",
        user_id="user-a",
        safety_settings={"pii_redaction": "on"},
        cache=LLMCacheOptions(scope="safe-cache"),
    )
    scoped_request = base_request.model_copy(update={"tenant_id": "tenant-b"})
    cache_scope_request = base_request.model_copy(
        update={"cache": LLMCacheOptions(scope="tenant-cache")},
    )
    prompt_request = base_request.model_copy(update={"prompt_version": "rag-answer:v2"})
    safety_request = base_request.model_copy(
        update={"safety_settings": {"pii_redaction": "off"}},
    )

    base_key = LLMCacheKey.from_request(provider="fake", request=base_request)

    assert base_key.model == "fake-chat"
    assert base_key.prompt_version == "rag-answer:v1"
    assert base_key.tenant_id == "tenant-a"
    assert base_key.user_id == "user-a"
    assert base_key.cache_scope == "safe-cache"
    assert base_key != LLMCacheKey.from_request(provider="fake", request=scoped_request)
    assert base_key != LLMCacheKey.from_request(
        provider="fake", request=cache_scope_request
    )
    assert base_key != LLMCacheKey.from_request(provider="fake", request=prompt_request)
    assert base_key != LLMCacheKey.from_request(provider="fake", request=safety_request)


def test_llm_cache_key_can_use_effective_model_when_request_model_is_omitted():
    request = LLMRequest(messages=[ChatMessage(role="user", content="hello")])

    key = LLMCacheKey.from_request(
        provider="fake",
        request=request,
        default_model="fake-chat",
    )

    assert key.model == "fake-chat"
