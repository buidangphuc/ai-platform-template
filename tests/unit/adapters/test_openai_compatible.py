from types import SimpleNamespace

from app.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddingClient
from app.adapters.llm.openai_compatible import OpenAICompatibleLLMClient
from app.contracts.embeddings import EmbeddingRequest
from app.contracts.llm import ChatMessage, LLMRequest


class FakeChatCompletions:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None
        self.tool_calls: list[object] = []

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            model=kwargs["model"],
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="hello from provider",
                        tool_calls=self.tool_calls,
                    ),
                    finish_reason="stop",
                ),
            ],
            usage=SimpleNamespace(
                prompt_tokens=4,
                completion_tokens=3,
                total_tokens=7,
            ),
        )


class FakeEmbeddings:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            model=kwargs["model"],
            data=[
                SimpleNamespace(embedding=[0.1, 0.2]),
                SimpleNamespace(embedding=[0.3, 0.4]),
            ],
            usage=SimpleNamespace(prompt_tokens=5, total_tokens=5),
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat_completions = FakeChatCompletions()
        self.embeddings_create = FakeEmbeddings()
        self.chat = SimpleNamespace(completions=self.chat_completions)
        self.embeddings = self.embeddings_create


async def test_openai_compatible_llm_translates_contract_request():
    provider = FakeOpenAIClient()
    client = OpenAICompatibleLLMClient(
        client=provider,
        model="gpt-test",
    )

    response = await client.complete(
        LLMRequest(
            messages=[ChatMessage(role="user", content="hello")],
            temperature=0.2,
        ),
    )

    assert provider.chat_completions.kwargs == {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.2,
    }
    assert response.content == "hello from provider"
    assert response.model == "gpt-test"
    assert response.usage.total_tokens == 7


async def test_openai_compatible_llm_preserves_tool_calls():
    provider = FakeOpenAIClient()
    provider.chat_completions.tool_calls = [
        SimpleNamespace(
            id="call_1",
            type="function",
            function=SimpleNamespace(
                name="search_docs",
                arguments='{"query":"phase 3"}',
            ),
        )
    ]
    client = OpenAICompatibleLLMClient(
        client=provider,
        model="gpt-test",
    )

    response = await client.complete(
        LLMRequest(
            messages=[ChatMessage(role="user", content="hello")],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "search_docs"},
                }
            ],
        )
    )

    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "search_docs"
    assert response.tool_calls[0].arguments == '{"query":"phase 3"}'


async def test_openai_compatible_embeddings_translate_contract_request():
    provider = FakeOpenAIClient()
    client = OpenAICompatibleEmbeddingClient(
        client=provider,
        model="embedding-test",
    )

    response = await client.embed(EmbeddingRequest(texts=["alpha", "beta"]))

    assert provider.embeddings_create.kwargs == {
        "model": "embedding-test",
        "input": ["alpha", "beta"],
    }
    assert response.model == "embedding-test"
    assert response.vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert response.usage.input_tokens == 5
