from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from app.modules.ai.llm.runtime import build_chat_model


async def test_build_chat_model_defaults_to_langchain_core_local_model(
    test_settings,
):
    model = build_chat_model(test_settings)

    response = await model.ainvoke([HumanMessage(content="hello")])

    assert isinstance(model, BaseChatModel)
    assert isinstance(model, FakeListChatModel)
    assert response.content == "fake response"


async def test_build_chat_model_delegates_provider_and_model_to_init_chat_model(
    monkeypatch,
    test_settings,
):
    calls: dict[str, str] = {}

    def fake_init_chat_model(target: str) -> BaseChatModel:
        calls["target"] = target
        return FakeListChatModel(responses=["provider-chat response"])

    monkeypatch.setattr(
        "app.modules.ai.llm.router.init_chat_model",
        fake_init_chat_model,
    )
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "openai:gpt-4.1-mini",
        }
    )

    model = build_chat_model(settings)
    response = await model.ainvoke([HumanMessage(content="hello")])

    assert calls == {"target": "openai:gpt-4.1-mini"}
    assert response.content == "provider-chat response"
