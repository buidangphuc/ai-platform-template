import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    GenericFakeChatModel,
)
from langchain_core.messages import AIMessage, HumanMessage

from app.core.errors import ServiceUnavailableError
from app.core.resilience import BreakerState
from app.modules.ai.llm.langfuse import LLMTraceContext
from app.modules.ai.llm.runtime import build_llm_instance


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _FailingModel(FakeListChatModel):
    error: Exception

    def _call(self, *args, **kwargs):
        raise self.error


def _model(target: str, failures: dict[str, Exception]) -> BaseChatModel:
    if target in failures:
        return _FailingModel(responses=[target], error=failures[target])
    return FakeListChatModel(responses=[target])


def _instance(test_settings, failures: dict[str, Exception], **overrides):
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "primary",
            "CHAT_FALLBACK_MODELS": "secondary",
            "LLM_BREAKER_FAILURE_THRESHOLD": 2,
            **overrides,
        }
    )
    return build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: _model(target, failures),
    )


async def test_instance_defaults_to_langchain_core_local_model(test_settings):
    instance = build_llm_instance(test_settings, instance_id="t", service_name="s")

    response = await instance.ainvoke([HumanMessage(content="hello")])

    assert isinstance(instance.chat_model(), FakeListChatModel)
    assert response.content == "fake response"


async def test_default_model_builder_passes_bounded_call_settings(
    monkeypatch,
    test_settings,
):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_init_chat_model(target: str, **kwargs: object) -> BaseChatModel:
        calls.append((target, kwargs))
        return FakeListChatModel(responses=["provider-chat response"])

    # init_chat_model is imported lazily inside the builder (the [ai] extra
    # boundary) — patch it at its source module.
    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init_chat_model)
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "openai:gpt-4.1-mini",
            "LLM_MAX_TOKENS": 777,
            "LLM_TIMEOUT_SECONDS": 12.5,
            "LLM_MAX_RETRIES": 0,
        }
    )
    instance = build_llm_instance(settings, instance_id="t", service_name="s")

    response = await instance.ainvoke([HumanMessage(content="hello")])

    assert calls == [
        (
            "openai:gpt-4.1-mini",
            {"max_tokens": 777, "timeout": 12.5, "max_retries": 0},
        )
    ]
    assert response.content == "provider-chat response"


async def test_ainvoke_uses_primary_and_reports_success(test_settings):
    instance = _instance(test_settings, {})

    response = await instance.ainvoke([HumanMessage(content="hi")])

    assert response.content == "primary"
    assert (
        instance.router._breakers[("default", "primary")].state is BreakerState.CLOSED
    )


async def test_ainvoke_fails_over_to_secondary_on_transient_primary_error(
    test_settings,
):
    instance = _instance(test_settings, {"primary": _StatusError(503)})

    response = await instance.ainvoke([HumanMessage(content="hi")])

    assert response.content == "secondary"
    assert instance.router._breakers[("default", "primary")].failure_count == 1


async def test_breaker_opens_so_later_calls_skip_the_failing_primary(test_settings):
    instance = _instance(test_settings, {"primary": TimeoutError()})

    for _ in range(2):
        await instance.ainvoke([HumanMessage(content="hi")])

    assert instance.router._breakers[("default", "primary")].state is BreakerState.OPEN
    assert instance.router.select_target("default") == "secondary"


async def test_ainvoke_does_not_fail_over_on_deterministic_error(test_settings):
    instance = _instance(test_settings, {"primary": _StatusError(400)})

    with pytest.raises(_StatusError):
        await instance.ainvoke([HumanMessage(content="hi")])

    assert (
        instance.router._breakers[("default", "primary")].state is BreakerState.CLOSED
    )
    assert instance.router._breakers[("default", "primary")].failure_count == 0


async def test_ainvoke_raises_when_secondary_also_fails(test_settings):
    instance = _instance(
        test_settings,
        {"primary": _StatusError(503), "secondary": _StatusError(503)},
    )

    with pytest.raises(_StatusError):
        await instance.ainvoke([HumanMessage(content="hi")])


def _chain_instance(test_settings, failures: dict[str, Exception]):
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "a",
            "CHAT_FALLBACK_MODELS": "b, c",
            "LLM_BREAKER_FAILURE_THRESHOLD": 1,
        }
    )
    built: list[str] = []

    def build(target: str) -> BaseChatModel:
        built.append(target)
        return _model(target, failures)

    instance = build_llm_instance(
        settings, instance_id="t", service_name="test", model_builder=build
    )
    return instance, built


async def test_ainvoke_walks_the_whole_chain_on_transient_errors(test_settings):
    instance, _ = _chain_instance(
        test_settings, {"a": _StatusError(503), "b": TimeoutError()}
    )

    response = await instance.ainvoke([HumanMessage(content="hi")])

    assert response.content == "c"
    router = instance.router
    assert router._breakers[("default", "a")].state is BreakerState.OPEN
    assert router._breakers[("default", "b")].state is BreakerState.OPEN
    assert router._breakers[("default", "c")].state is BreakerState.CLOSED


async def test_ainvoke_skips_targets_whose_breaker_is_open(test_settings):
    instance, built = _chain_instance(test_settings, {"a": TimeoutError()})
    await instance.ainvoke([HumanMessage(content="hi")])
    built.clear()
    instance.router._models.clear()

    response = await instance.ainvoke([HumanMessage(content="hi")])

    assert response.content == "b"
    assert built == ["b"]  # "a" was never even built, let alone called


async def test_ainvoke_stops_on_a_deterministic_error_mid_chain(test_settings):
    instance, built = _chain_instance(
        test_settings, {"a": _StatusError(503), "b": _StatusError(400)}
    )

    with pytest.raises(_StatusError, match="400"):
        await instance.ainvoke([HumanMessage(content="hi")])

    assert "c" not in built


async def test_ainvoke_raises_the_last_error_when_the_chain_is_exhausted(
    test_settings,
):
    instance, _ = _chain_instance(
        test_settings,
        {"a": _StatusError(500), "b": _StatusError(502), "c": _StatusError(503)},
    )

    with pytest.raises(_StatusError, match="503"):
        await instance.ainvoke([HumanMessage(content="hi")])


async def test_ainvoke_raises_unavailable_when_every_breaker_is_open(test_settings):
    instance, _ = _chain_instance(
        test_settings,
        {"a": _StatusError(500), "b": _StatusError(500), "c": _StatusError(500)},
    )
    with pytest.raises(_StatusError):
        await instance.ainvoke([HumanMessage(content="hi")])

    with pytest.raises(ServiceUnavailableError):
        await instance.ainvoke([HumanMessage(content="hi")])


async def test_ainvoke_applies_trace_config_per_call(test_settings):
    seen: list[object] = []

    class _Recording(GenericFakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.append(run_manager.metadata if run_manager else None)
            return super()._generate(messages, stop, run_manager, **kwargs)

    settings = test_settings.model_copy(update={"CHAT_MODEL": "m"})
    instance = build_llm_instance(
        settings,
        instance_id="traced",
        service_name="svc",
        model_builder=lambda _t: _Recording(messages=iter([AIMessage(content="ok")])),
    )

    await instance.ainvoke(
        [HumanMessage(content="hi")],
        context=LLMTraceContext(run_name="r", request_id="req-1"),
    )

    metadata = seen[0]
    assert isinstance(metadata, dict)
    assert metadata["llm_instance_id"] == "traced"
    assert metadata["request_id"] == "req-1"


def test_build_llm_instance_keeps_router_and_tracker_separate(test_settings):
    instance = build_llm_instance(
        test_settings,
        instance_id="search-rerank",
        service_name="search",
        tags=("retrieval",),
    )
    config = instance.trace_config(LLMTraceContext(run_name="search.rerank"))

    assert instance.tracker.instance_id == "search-rerank"
    assert instance.tracker.service_name == "search"
    assert "retrieval" in config["tags"]
