import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.adapters.langchain.bridges import LangChainEmbeddingClient, LangChainLLMClient
from app.adapters.langchain.chat_models import TemplateFakeChatModel, build_chat_model
from app.adapters.langchain.embeddings import build_embeddings
from app.contracts.embeddings import EmbeddingRequest
from app.contracts.llm import ChatMessage, LLMRequest


async def test_build_chat_model_returns_langchain_chat_model_for_fake_provider(
    test_settings,
):
    model = build_chat_model(test_settings)

    response = await model.ainvoke([HumanMessage(content="hello")])

    assert isinstance(model, BaseChatModel)
    assert response.content.startswith("fake-chat response:")
    assert response.usage_metadata["input_tokens"] > 0


async def test_build_chat_model_uses_langchain_init_chat_model(
    monkeypatch,
    test_settings,
):
    calls: dict[str, str | None] = {}

    def fake_init_chat_model(
        *,
        model: str,
        model_provider: str | None = None,
    ) -> BaseChatModel:
        calls["model"] = model
        calls["model_provider"] = model_provider
        return TemplateFakeChatModel(model_name="langchain-chat")

    monkeypatch.setattr(
        "app.adapters.langchain.chat_models.init_chat_model",
        fake_init_chat_model,
    )
    settings = test_settings.model_copy(
        update={
            "LLM_PROVIDER": "langchain",
            "CHAT_MODEL": "gpt-test",
            "CHAT_MODEL_PROVIDER": "openai",
        }
    )

    model = build_chat_model(settings)
    response = await model.ainvoke([HumanMessage(content="hello")])

    assert calls == {"model": "gpt-test", "model_provider": "openai"}
    assert response.content.startswith("langchain-chat response:")


def test_build_chat_model_rejects_unknown_provider_even_with_chat_model(test_settings):
    settings = test_settings.model_copy(
        update={
            "LLM_PROVIDER": "unknown",
            "CHAT_MODEL": "gpt-test",
        }
    )

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        build_chat_model(settings)


async def test_build_embeddings_returns_langchain_embeddings_for_fake_provider(
    test_settings,
):
    embeddings = build_embeddings(test_settings)

    vectors = await embeddings.aembed_documents(["alpha", "beta"])

    assert isinstance(embeddings, Embeddings)
    assert len(vectors) == 2
    assert len(vectors[0]) == test_settings.FAKE_EMBEDDING_DIMENSIONS


async def test_langchain_llm_bridge_preserves_existing_llm_contract(test_settings):
    bridge = LangChainLLMClient(
        chat_model=build_chat_model(test_settings),
        default_model="fake-chat",
    )

    response = await bridge.complete(
        LLMRequest(messages=[ChatMessage(role="user", content="bridge")])
    )

    assert response.content.startswith("fake-chat response:")
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
