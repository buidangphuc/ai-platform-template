"""LLMInstance records one observation per ainvoke/astream call."""

import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from loguru import logger
from pydantic import Field

from app.core.telemetry import FanOutSink, LlmObservation, LogLlmSink
from app.modules.ai.llm.runtime import (
    LLMDeadlineExceeded,
    StreamTimeoutError,
    build_llm_instance,
)

SECRET = "do-not-record-this-prompt"  # pragma: allowlist secret


class _Sink:
    def __init__(self) -> None:
        self.observations: list[LlmObservation] = []

    def record_llm(self, observation: LlmObservation) -> None:
        self.observations.append(observation)


def _chunk(text: str, **fields: object) -> AIMessageChunk:
    return AIMessageChunk(content=text, **fields)  # type: ignore[arg-type]


class _Model(FakeListChatModel):
    script: list[object] = Field(default_factory=list)
    reply: AIMessage | None = None
    error: Exception | None = None
    closed: list[bool] = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.error:
            raise self.error
        reply = self.reply or AIMessage(content="ok")
        return ChatResult(generations=[ChatGeneration(message=reply)])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            for step in self.script:
                if isinstance(step, Exception):
                    raise step
                if isinstance(step, AIMessageChunk):
                    yield ChatGenerationChunk(message=step)
                else:
                    await asyncio.sleep(float(step))  # type: ignore[arg-type]
        finally:
            self.closed.append(True)


def _instance(test_settings, model: _Model, sink: _Sink, **overrides):
    settings = test_settings.model_copy(update={"CHAT_MODEL": "m", **overrides})
    return build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: model,
        sink=sink,
    )


def _model(**fields: object) -> _Model:
    return _Model(responses=["x"], closed=[], **fields)


USAGE = {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}


async def test_llm_observation_ainvoke_records_one_sync_observation(test_settings):
    sink = _Sink()
    reply = AIMessage(
        content=SECRET,
        usage_metadata=USAGE,
        response_metadata={"model_name": "gpt", "finish_reason": "stop"},
    )
    instance = _instance(test_settings, _model(reply=reply), sink)

    await instance.ainvoke([HumanMessage(content=SECRET)])

    (obs,) = sink.observations
    assert (obs.mode, obs.outcome, obs.model, obs.finish_reason) == (
        "sync",
        "ok",
        "gpt",
        "stop",
    )
    assert (obs.input_tokens, obs.output_tokens, obs.total_tokens) == (2, 3, 5)
    assert obs.ttft_s is None
    assert SECRET not in repr(obs)


async def test_llm_observation_model_falls_back_to_target(test_settings):
    sink = _Sink()
    instance = _instance(test_settings, _model(), sink)

    await instance.ainvoke([HumanMessage(content="hi")])

    assert sink.observations[0].model == "m"


async def test_llm_observation_failover_is_still_one_observation(test_settings):
    sink = _Sink()
    settings = test_settings.model_copy(
        update={"CHAT_MODEL": "a", "CHAT_FALLBACK_MODELS": "b"}
    )
    models = {
        "a": _model(error=TimeoutError("down")),
        "b": _model(reply=AIMessage(content="ok")),
    }
    instance = build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=models.__getitem__,
        sink=sink,
    )

    await instance.ainvoke([HumanMessage(content="hi")])

    (obs,) = sink.observations
    assert (obs.outcome, obs.model) == ("ok", "b")


async def test_llm_observation_ainvoke_failure_is_labelled_error(test_settings):
    sink = _Sink()
    instance = _instance(test_settings, _model(error=RuntimeError("boom")), sink)

    with pytest.raises(RuntimeError):
        await instance.ainvoke([HumanMessage(content="hi")])

    (obs,) = sink.observations
    assert (obs.outcome, obs.model) == ("error", None)


async def test_llm_observation_ainvoke_deadline_is_timeout(test_settings):
    sink = _Sink()

    class _Slow(_Model):
        async def _agenerate(self, *args, **kwargs):
            await asyncio.sleep(5)

    instance = _instance(
        test_settings,
        _Slow(responses=["x"], closed=[]),
        sink,
        LLM_CHAIN_DEADLINE_SECONDS=0.1,
        LLM_TIMEOUT_SECONDS=0.1,
    )

    with pytest.raises(LLMDeadlineExceeded):
        await instance.ainvoke([HumanMessage(content="hi")])

    assert [o.outcome for o in sink.observations] == ["timeout"]


async def test_llm_observation_stream_records_ttft_usage_and_model(test_settings):
    sink = _Sink()
    model = _model(
        script=[
            _chunk("a", response_metadata={"model_name": "gpt"}),
            _chunk(
                "b", usage_metadata=USAGE, response_metadata={"finish_reason": "stop"}
            ),
        ]
    )
    instance = _instance(test_settings, model, sink)

    chunks = [c async for c in instance.astream([HumanMessage(content=SECRET)])]

    assert len(chunks) >= 2
    (obs,) = sink.observations
    assert (obs.mode, obs.outcome, obs.model, obs.finish_reason) == (
        "stream",
        "ok",
        "gpt",
        "stop",
    )
    assert (obs.input_tokens, obs.output_tokens, obs.total_tokens) == (2, 3, 5)
    assert obs.ttft_s is not None
    assert SECRET not in repr(obs)
    assert model.closed == [True]


async def test_llm_observation_stream_failure_is_labelled_error(test_settings):
    sink = _Sink()
    instance = _instance(test_settings, _model(script=[RuntimeError("boom")]), sink)

    with pytest.raises(RuntimeError):
        [c async for c in instance.astream([HumanMessage(content="hi")])]

    assert [o.outcome for o in sink.observations] == ["error"]


async def test_llm_observation_first_token_timeout(test_settings):
    sink = _Sink()
    model = _model(script=[5])
    instance = _instance(test_settings, model, sink)

    with pytest.raises(StreamTimeoutError) as caught:
        [
            c
            async for c in instance.astream(
                [HumanMessage(content="hi")], first_token_timeout=0.05
            )
        ]

    assert (caught.value.code, caught.value.status_code) == ("stream_timeout", 504)
    assert [o.outcome for o in sink.observations] == ["timeout"]
    assert model.closed == [True]


async def test_llm_observation_idle_timeout_after_first_chunk(test_settings):
    sink = _Sink()
    instance = _instance(test_settings, _model(script=[_chunk("a"), 5]), sink)
    seen: list[str] = []

    with pytest.raises(StreamTimeoutError):
        async for chunk in instance.astream(
            [HumanMessage(content="hi")], idle_timeout=0.05
        ):
            seen.append(str(chunk.content))

    assert seen == ["a"]
    assert [o.outcome for o in sink.observations] == ["timeout"]


async def test_llm_observation_model_raised_timeout_is_an_error(test_settings):
    sink = _Sink()
    instance = _instance(test_settings, _model(script=[TimeoutError("up")]), sink)

    with pytest.raises(TimeoutError):
        [
            c
            async for c in instance.astream(
                [HumanMessage(content="hi")], first_token_timeout=5
            )
        ]

    assert [o.outcome for o in sink.observations] == ["error"]


async def test_llm_observation_closing_the_stream_is_disconnected(test_settings):
    sink = _Sink()
    model = _model(script=[_chunk("a"), 5])
    instance = _instance(test_settings, model, sink)

    stream = instance.astream([HumanMessage(content="hi")])
    await anext(stream)
    await stream.aclose()

    assert [o.outcome for o in sink.observations] == ["disconnected"]
    assert model.closed == [True]


async def test_llm_observation_cancelled_stream_is_disconnected(test_settings):
    sink = _Sink()
    model = _model(script=[_chunk("a"), 5])
    instance = _instance(test_settings, model, sink)
    first = asyncio.Event()

    async def consume() -> None:
        async for _ in instance.astream([HumanMessage(content="hi")]):
            first.set()

    task = asyncio.create_task(consume())
    await first.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [o.outcome for o in sink.observations] == ["disconnected"]
    assert model.closed == [True]


async def test_llm_observation_stream_deadline_is_timeout(test_settings):
    sink = _Sink()
    instance = _instance(
        test_settings,
        _model(script=[5]),
        sink,
        LLM_CHAIN_DEADLINE_SECONDS=0.1,
        LLM_TIMEOUT_SECONDS=0.1,
    )

    with pytest.raises(LLMDeadlineExceeded):
        [c async for c in instance.astream([HumanMessage(content="hi")])]

    assert [o.outcome for o in sink.observations] == ["timeout"]


def test_log_sink_emits_the_completion_line_and_bound_fields() -> None:
    records: list[dict] = []
    handle = logger.add(lambda m: records.append(m.record), format="{message}")
    try:
        LogLlmSink().record_llm(
            LlmObservation(
                mode="stream",
                outcome="ok",
                started_ns=0,
                duration_s=0.0123,
                ttft_s=0.005,
                model="m",
                finish_reason="stop",
                input_tokens=2,
                output_tokens=3,
                total_tokens=5,
            )
        )
    finally:
        logger.remove(handle)

    (record,) = records
    assert record["message"] == (
        "completion mode=stream outcome=ok model=m duration_ms=12.3 ttft_ms=5.0 "
        "finish_reason=stop input_tokens=2 output_tokens=3 total_tokens=5"
    )
    assert record["extra"]["event"] == "completion"
    assert record["extra"]["duration_ms"] == 12.3


def test_fan_out_sink_reaches_every_sink() -> None:
    a, b = _Sink(), _Sink()
    obs = LlmObservation(
        mode="sync",
        outcome="ok",
        started_ns=0,
        duration_s=0.1,
        ttft_s=None,
        model=None,
        finish_reason=None,
        input_tokens=None,
        output_tokens=None,
    )

    FanOutSink([a, b]).record_llm(obs)

    assert a.observations == [obs] == b.observations
