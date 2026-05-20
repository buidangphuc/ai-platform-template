from langchain_core.embeddings import Embeddings
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    ParrotFakeChatModel,
)
from langchain_core.messages import HumanMessage

from app.adapters.langchain.bridges import LangChainEmbeddingClient, LangChainLLMClient
from app.adapters.langchain.chat_models import build_chat_model
from app.adapters.langchain.embeddings import build_embeddings
from app.contracts.embeddings import EmbeddingRequest
from app.contracts.llm import ChatMessage, LLMRequest


async def test_build_chat_model_defaults_to_langchain_core_local_model(
    test_settings,
):
    model = build_chat_model(test_settings)

    response = await model.ainvoke([HumanMessage(content="hello")])

    assert isinstance(model, BaseChatModel)
    assert isinstance(model, ParrotFakeChatModel)
    assert response.content == "hello"


async def test_build_chat_model_uses_langchain_init_chat_model(
    monkeypatch,
    test_settings,
):
    calls: dict[str, str] = {}

    def fake_init_chat_model(
        *,
        model: str,
    ) -> BaseChatModel:
        calls["model"] = model
        return FakeListChatModel(responses=["langchain-chat response"])

    monkeypatch.setattr(
        "app.adapters.langchain.chat_models.init_chat_model",
        fake_init_chat_model,
    )
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "gpt-test",
        }
    )

    model = build_chat_model(settings)
    response = await model.ainvoke([HumanMessage(content="hello")])

    assert calls == {"model": "gpt-test"}
    assert response.content == "langchain-chat response"


async def test_build_embeddings_defaults_to_langchain_core_local_embeddings(
    test_settings,
):
    embeddings = build_embeddings(test_settings)

    vectors = await embeddings.aembed_documents(["alpha", "beta"])

    assert isinstance(embeddings, DeterministicFakeEmbedding)
    assert len(vectors) == 2
    assert len(vectors[0]) == 16


async def test_build_embeddings_uses_langchain_init_embeddings(
    monkeypatch,
    test_settings,
):
    calls: dict[str, str] = {}

    def fake_init_embeddings(*, model: str) -> Embeddings:
        calls["model"] = model
        return DeterministicFakeEmbedding(size=8)

    monkeypatch.setattr(
        "app.adapters.langchain.embeddings.init_embeddings",
        fake_init_embeddings,
    )
    settings = test_settings.model_copy(
        update={
            "EMBEDDING_MODEL": "text-embedding-test",
        }
    )

    embeddings = build_embeddings(settings)
    vectors = await embeddings.aembed_documents(["alpha"])

    assert calls == {"model": "text-embedding-test"}
    assert len(vectors[0]) == 8


async def test_langchain_llm_bridge_preserves_existing_llm_contract(test_settings):
    bridge = LangChainLLMClient(
        chat_model=build_chat_model(test_settings),
        default_model="fake-chat",
    )

    response = await bridge.complete(
        LLMRequest(messages=[ChatMessage(role="user", content="bridge")])
    )

    assert response.content == "bridge"
    assert response.model == "fake-chat"
    assert response.usage.total_tokens > 0


async def test_langchain_embedding_bridge_preserves_existing_embedding_contract(
    test_settings,
):
    bridge = LangChainEmbeddingClient(
        embeddings=build_embeddings(test_settings),
        default_model="fake-embedding",
    )

    response = await bridge.embed(EmbeddingRequest(texts=["alpha"]))

    assert response.model == "fake-embedding"
    assert len(response.vectors) == 1
