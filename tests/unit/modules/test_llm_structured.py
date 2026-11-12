import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.core.resilience import BreakerState
from app.modules.ai.llm.runtime import StructuredOutputError, build_llm_instance


class Listing(BaseModel):
    title: str
    rooms: int


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _FailingModel(FakeListChatModel):
    error: Exception

    def _call(self, *args, **kwargs):
        raise self.error


class _RecordingModel(FakeListChatModel):
    seen: list

    def _call(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._call(messages, *args, **kwargs)


class _Sink:
    def __init__(self) -> None:
        self.observations: list = []

    def record_llm(self, observation) -> None:
        self.observations.append(observation)


def _instance(test_settings, models: dict[str, BaseChatModel], sink=None, **overrides):
    settings = test_settings.model_copy(update={"CHAT_MODEL": "primary", **overrides})
    kwargs = {"sink": sink} if sink is not None else {}
    return build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: models[target],
        **kwargs,
    )


def _reply(text: str) -> dict[str, BaseChatModel]:
    return {"primary": FakeListChatModel(responses=[text])}


async def test_valid_json_returns_schema_instance(test_settings):
    instance = _instance(test_settings, _reply('{"title": "Flat", "rooms": 2}'))

    result = await instance.astructured(Listing, "describe")

    assert result == Listing(title="Flat", rooms=2)


async def test_fenced_json_is_parsed(test_settings):
    reply = 'Here you go:\n```json\n{"title": "Flat", "rooms": 3}\n```\n'
    instance = _instance(test_settings, _reply(reply))

    result = await instance.astructured(Listing, "describe")

    assert result == Listing(title="Flat", rooms=3)


@pytest.mark.parametrize(
    "reply",
    ["SECRET-not-json", '{"title": "SECRET-x", "rooms": "many"}', '["SECRET"]'],
)
async def test_invalid_reply_raises_without_leaking_text(test_settings, reply):
    instance = _instance(test_settings, _reply(reply))

    with pytest.raises(StructuredOutputError) as caught:
        await instance.astructured(Listing, "describe")

    assert "Listing" in str(caught.value)
    assert "SECRET" not in str(caught.value)


async def test_fallback_after_transient_primary_failure(test_settings):
    sink = _Sink()
    models = {
        "primary": _FailingModel(responses=["x"], error=_StatusError(503)),
        "secondary": FakeListChatModel(responses=['{"title": "B", "rooms": 1}']),
    }
    instance = _instance(
        test_settings, models, sink=sink, CHAT_FALLBACK_MODELS="secondary"
    )

    result = await instance.astructured(Listing, "describe")

    assert result == Listing(title="B", rooms=1)
    assert [o.mode for o in sink.observations] == ["sync"]
    assert [o.outcome for o in sink.observations] == ["ok"]
    assert instance.router._breaker("default", "primary").state is BreakerState.CLOSED


async def test_deterministic_error_does_not_fail_over(test_settings):
    models = {
        "primary": _FailingModel(responses=["x"], error=_StatusError(400)),
        "secondary": FakeListChatModel(responses=['{"title": "B", "rooms": 1}']),
    }
    instance = _instance(test_settings, models, CHAT_FALLBACK_MODELS="secondary")

    with pytest.raises(_StatusError):
        await instance.astructured(Listing, "describe")


async def test_vision_role_uses_configured_model(test_settings):
    models = {
        "primary": FakeListChatModel(responses=["wrong"]),
        "vision-model": FakeListChatModel(responses=['{"title": "V", "rooms": 4}']),
    }
    instance = _instance(test_settings, models, VISION_CHAT_MODEL="vision-model")

    result = await instance.astructured(Listing, "look", role="vision")

    assert result == Listing(title="V", rooms=4)
    assert instance.router.chain("vision") == ("vision-model",)


async def test_vision_role_falls_back_to_default_chain_when_unset(test_settings):
    instance = _instance(
        test_settings,
        {
            "primary": FakeListChatModel(responses=['{"title": "D", "rooms": 5}']),
            "secondary": FakeListChatModel(responses=["x"]),
        },
        CHAT_FALLBACK_MODELS="secondary",
        VISION_CHAT_MODEL="",
    )

    result = await instance.astructured(Listing, "look", role="vision")

    assert result == Listing(title="D", rooms=5)
    assert instance.router.chain("vision") == instance.router.chain("default")


async def test_multimodal_message_passes_through_with_instruction(test_settings):
    model = _RecordingModel(responses=['{"title": "M", "rooms": 1}'], seen=[])
    instance = _instance(test_settings, {"primary": model})
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    message = HumanMessage(content=[{"type": "text", "text": "what is this"}, image])

    await instance.astructured(Listing, [message])

    sent = model.seen[0]
    assert sent[0] is message
    assert sent[0].content == [{"type": "text", "text": "what is this"}, image]
    assert len(sent) == 2
    assert "rooms" in sent[1].content


async def test_string_input_gets_schema_instruction(test_settings):
    model = _RecordingModel(responses=['{"title": "S", "rooms": 1}'], seen=[])
    instance = _instance(test_settings, {"primary": model})

    await instance.astructured(Listing, "describe")

    text = str(model.seen[0])
    assert "describe" in text
    assert "JSON" in text
    assert "rooms" in text
