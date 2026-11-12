import asyncio
import time

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    GenericFakeChatModel,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.resilience import BreakerState, is_transient_error
from app.modules.ai.llm.langfuse import LLMTraceContext
from app.modules.ai.llm.runtime import (
    LLMDeadlineExceeded,
    StreamTimeoutError,
    build_llm_instance,
)


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


class _SleepingModel(FakeListChatModel):
    delay: float

    async def _agenerate(self, *args, **kwargs):
        await asyncio.sleep(self.delay)
        return await super()._agenerate(*args, **kwargs)


def _deadline_instance(test_settings, delays: dict[str, float], failures=None):
    failures = failures or {}
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "a",
            "CHAT_FALLBACK_MODELS": "b, c",
            "LLM_BREAKER_FAILURE_THRESHOLD": 1,
            "LLM_CHAIN_DEADLINE_SECONDS": 0.4,
        }
    )
    called: list[str] = []

    def build(target: str) -> BaseChatModel:
        if target in failures:
            return _model(target, failures)
        called.append(target)
        return _SleepingModel(responses=[target], delay=delays.get(target, 0))

    instance = build_llm_instance(
        settings, instance_id="t", service_name="test", model_builder=build
    )
    return instance, called


async def test_chain_deadline_stops_walking_instead_of_paying_every_hop(test_settings):
    instance, called = _deadline_instance(
        test_settings, {"a": 0.3, "b": 5, "c": 5}, {"a": TimeoutError()}
    )
    started = time.monotonic()

    with pytest.raises(LLMDeadlineExceeded):
        await instance.ainvoke([HumanMessage(content="hi")])

    assert time.monotonic() - started < 1.0  # b would have slept 5s
    assert "c" not in called


async def test_deadline_cut_attempt_does_not_count_against_its_breaker(test_settings):
    instance, _ = _deadline_instance(test_settings, {"b": 5}, {"a": _StatusError(503)})

    with pytest.raises(LLMDeadlineExceeded):
        await instance.ainvoke([HumanMessage(content="hi")])

    breakers = instance.router._breakers
    assert breakers[("default", "a")].state is BreakerState.OPEN  # its own 503
    assert breakers[("default", "b")].failure_count == 0
    assert breakers[("default", "b")].state is BreakerState.CLOSED


async def test_deadline_error_is_a_transient_504(test_settings):
    instance, _ = _deadline_instance(test_settings, {"a": 5})

    with pytest.raises(LLMDeadlineExceeded) as raised:
        await instance.ainvoke([HumanMessage(content="hi")])

    assert raised.value.status_code == 504
    assert raised.value.code == "llm_deadline_exceeded"
    assert is_transient_error(raised.value)


async def test_a_call_inside_the_deadline_is_unaffected(test_settings):
    instance, _ = _deadline_instance(test_settings, {"a": 0.05})

    response = await instance.ainvoke([HumanMessage(content="hi")])

    assert response.content == "a"


class APITimeoutError(Exception):
    pass


class _SdkTimeoutModel(FakeListChatModel):
    attempt_seconds: float
    attempts: int

    async def _agenerate(self, *args, **kwargs):
        for _ in range(self.attempts):
            await asyncio.sleep(self.attempt_seconds)
        raise APITimeoutError("Request timed out.")


async def test_hung_primary_reaches_the_fallback_within_the_deadline(test_settings):
    scale = 0.01
    defaults = {
        name: Settings.model_fields[name].default
        for name in (
            "LLM_TIMEOUT_SECONDS",
            "LLM_MAX_RETRIES",
            "LLM_CHAIN_DEADLINE_SECONDS",
        )
    }
    timeout = defaults["LLM_TIMEOUT_SECONDS"] * scale
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "primary",
            "CHAT_FALLBACK_MODELS": "secondary",
            "LLM_TIMEOUT_SECONDS": timeout,
            "LLM_MAX_RETRIES": defaults["LLM_MAX_RETRIES"],
            "LLM_CHAIN_DEADLINE_SECONDS": defaults["LLM_CHAIN_DEADLINE_SECONDS"]
            * scale,
        }
    )

    budget = timeout * (settings.LLM_MAX_RETRIES + 1)
    assert settings.LLM_CHAIN_DEADLINE_SECONDS - budget >= 0.3

    def build(target: str) -> BaseChatModel:
        if target == "primary":
            return _SdkTimeoutModel(
                responses=[target],
                attempt_seconds=timeout,
                attempts=settings.LLM_MAX_RETRIES + 1,
            )
        return FakeListChatModel(responses=[target])

    instance = build_llm_instance(
        settings, instance_id="t", service_name="test", model_builder=build
    )

    response = await instance.ainvoke([HumanMessage(content="hi")])

    assert response.content == "secondary"
    assert instance.router._breakers[("default", "primary")].failure_count == 1


class _StreamModel(FakeListChatModel):
    script: list[object]

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        for step in self.script:
            if isinstance(step, Exception):
                raise step
            yield ChatGenerationChunk(message=AIMessageChunk(content=str(step)))


def _stream_instance(test_settings, scripts: dict[str, list[object]]):
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": "primary",
            "CHAT_FALLBACK_MODELS": "secondary",
            "LLM_BREAKER_FAILURE_THRESHOLD": 2,
        }
    )
    return build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: _StreamModel(
            responses=[target], script=scripts[target]
        ),
    )


async def _collect(instance, **kwargs) -> list[str]:
    return [
        str(chunk.content)
        async for chunk in instance.astream([HumanMessage(content="hi")], **kwargs)
        if chunk.content
    ]


async def test_astream_fails_over_before_first_chunk(test_settings):
    instance = _stream_instance(
        test_settings,
        {"primary": [_StatusError(503)], "secondary": ["s1", "s2"]},
    )

    assert await _collect(instance) == ["s1", "s2"]

    breakers = instance.router._breakers
    assert breakers[("default", "primary")].failure_count == 1
    assert breakers[("default", "secondary")].failure_count == 0


async def test_astream_no_failover_after_first_chunk(test_settings):
    instance = _stream_instance(
        test_settings,
        {"primary": ["p1", _StatusError(503)], "secondary": ["s1"]},
    )
    seen: list[str] = []

    with pytest.raises(_StatusError):
        async for chunk in instance.astream([HumanMessage(content="hi")]):
            seen.append(str(chunk.content))

    assert seen == ["p1"]
    breakers = instance.router._breakers
    assert breakers[("default", "primary")].failure_count == 1
    assert ("default", "secondary") not in breakers or (
        breakers[("default", "secondary")].failure_count == 0
    )


async def test_astream_does_not_fail_over_on_deterministic_error(test_settings):
    instance = _stream_instance(
        test_settings,
        {"primary": [_StatusError(400)], "secondary": ["s1"]},
    )

    with pytest.raises(_StatusError):
        await _collect(instance)

    assert instance.router._breakers[("default", "primary")].failure_count == 0


async def test_astream_reports_success_and_skips_open_breakers(test_settings):
    instance = _stream_instance(
        test_settings,
        {"primary": [TimeoutError()], "secondary": ["s1"]},
    )
    for _ in range(2):
        await _collect(instance)

    assert instance.router._breakers[("default", "primary")].state is BreakerState.OPEN
    assert await _collect(instance) == ["s1"]


async def test_astream_raises_unavailable_when_every_breaker_is_open(test_settings):
    instance = _stream_instance(
        test_settings,
        {"primary": [_StatusError(503)], "secondary": [_StatusError(503)]},
    )
    for _ in range(2):
        with pytest.raises(_StatusError):
            await _collect(instance)

    with pytest.raises(ServiceUnavailableError):
        await _collect(instance)


class _SlowStartModel(_StreamModel):
    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        await asyncio.sleep(5)
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk


async def test_astream_honours_the_chain_deadline(test_settings):
    settings = test_settings.model_copy(
        update={"CHAT_MODEL": "a", "LLM_CHAIN_DEADLINE_SECONDS": 0.2}
    )
    instance = build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: _SlowStartModel(responses=[target], script=["x"]),
    )

    with pytest.raises(LLMDeadlineExceeded):
        await _collect(instance)


class _StalledStartModel(_StreamModel):
    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        await asyncio.sleep(5)
        yield ChatGenerationChunk(message=AIMessageChunk(content="never"))


def _stall_instance(test_settings, targets: dict[str, BaseChatModel], **overrides):
    settings = test_settings.model_copy(
        update={
            "CHAT_MODEL": next(iter(targets)),
            "CHAT_FALLBACK_MODELS": ",".join(list(targets)[1:]),
            "LLM_BREAKER_FAILURE_THRESHOLD": 2,
            **overrides,
        }
    )
    return build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: targets[target],
        sink=(sink := _CapturingSink()),
    ), sink


class _CapturingSink:
    def __init__(self) -> None:
        self.observations: list = []

    def record_llm(self, observation) -> None:
        self.observations.append(observation)


async def test_first_token_stall_fails_over_and_counts_for_the_breaker(test_settings):
    instance, sink = _stall_instance(
        test_settings,
        {
            "primary": _StalledStartModel(responses=["p"], script=["x"]),
            "secondary": _StreamModel(responses=["s"], script=["s1", "s2"]),
        },
    )

    assert await _collect(instance, first_token_timeout=0.05) == ["s1", "s2"]

    breakers = instance.router._breakers
    assert breakers[("default", "primary")].failure_count == 1
    assert breakers[("default", "secondary")].failure_count == 0
    assert [o.outcome for o in sink.observations] == ["ok"]


async def test_first_token_stall_without_fallback_raises_stream_timeout(test_settings):
    instance, sink = _stall_instance(
        test_settings,
        {"primary": _StalledStartModel(responses=["p"], script=["x"])},
    )

    with pytest.raises(StreamTimeoutError):
        await _collect(instance, first_token_timeout=0.05)

    assert [o.outcome for o in sink.observations] == ["timeout"]


async def test_first_token_stall_on_every_target_raises_stream_timeout(test_settings):
    instance, sink = _stall_instance(
        test_settings,
        {
            "primary": _StalledStartModel(responses=["p"], script=["x"]),
            "secondary": _StalledStartModel(responses=["s"], script=["x"]),
        },
    )

    with pytest.raises(StreamTimeoutError):
        await _collect(instance, first_token_timeout=0.05)

    assert [o.outcome for o in sink.observations] == ["timeout"]
