from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    ParrotFakeChatModel,
)
from langchain_core.messages import HumanMessage

from app.modules.llm.runtime import build_chat_model


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
        "app.modules.llm.runtime.init_chat_model",
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
