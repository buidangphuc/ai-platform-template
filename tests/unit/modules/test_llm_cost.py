import asyncio
import json

import pytest
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    GenericFakeChatModel,
)
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.core.telemetry import collect_llm_usage
from app.modules.ai.llm.runtime import build_llm_instance


class Reply(BaseModel):
    ok: bool


class _Sink:
    def __init__(self) -> None:
        self.observations: list = []

    def record_llm(self, observation) -> None:
        self.observations.append(observation)


def _message(
    model: str | None = "m",
    input_tokens: int | None = 1000,
    output_tokens: int | None = 500,
    text: str = '{"ok": true}',
) -> AIMessage:
    usage = (
        None
        if input_tokens is None or output_tokens is None
        else {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    )
    metadata = {"model_name": model} if model else {}
    return AIMessage(content=text, usage_metadata=usage, response_metadata=metadata)


def _instance(test_settings, messages, prices, sink=None, **overrides):
    settings = test_settings.model_copy(
        update={"CHAT_MODEL": "m", "LLM_PRICES": prices, **overrides}
    )
    return build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: GenericFakeChatModel(messages=iter(messages)),
        **({"sink": sink} if sink is not None else {}),
    )


def _prices(**table):
    from app.core.config.ai import ModelPrice

    return {name: ModelPrice(**values) for name, values in table.items()}


async def test_priced_call_costs_tokens_times_price_per_million(test_settings):
    sink = _Sink()
    instance = _instance(
        test_settings,
        [_message()],
        _prices(m={"input": 1.0, "output": 2.0}),
        sink=sink,
    )

    await instance.ainvoke("hi")

    assert sink.observations[0].cost_usd == pytest.approx(0.002, abs=1e-12)


async def test_unpriced_model_has_no_cost_and_the_call_succeeds(test_settings):
    sink = _Sink()
    instance = _instance(
        test_settings,
        [_message(model="other")],
        _prices(m={"input": 1.0, "output": 2.0}),
        sink=sink,
    )

    message = await instance.ainvoke("hi")

    assert message.text == '{"ok": true}'
    assert sink.observations[0].cost_usd is None
    assert sink.observations[0].input_tokens == 1000


async def test_unknown_usage_has_no_cost(test_settings):
    sink = _Sink()
    instance = _instance(
        test_settings,
        [_message(input_tokens=None)],
        _prices(m={"input": 1.0, "output": 2.0}),
        sink=sink,
    )

    await instance.ainvoke("hi")

    assert sink.observations[0].input_tokens is None
    assert sink.observations[0].cost_usd is None


async def test_empty_price_table_leaves_cost_none(test_settings):
    sink = _Sink()
    instance = _instance(test_settings, [_message()], {}, sink=sink)

    await instance.ainvoke("hi")

    assert sink.observations[0].cost_usd is None


async def test_collector_is_fed_with_the_default_noop_sink(test_settings):
    instance = _instance(
        test_settings,
        [_message()],
        _prices(m={"input": 1.0, "output": 2.0}),
    )

    with collect_llm_usage() as usage:
        await instance.ainvoke("hi")

    assert usage.calls == 1
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 500
    assert usage.cost_usd == pytest.approx(0.002, abs=1e-12)


async def test_collector_does_not_change_what_the_sink_receives(test_settings):
    sink = _Sink()
    instance = _instance(
        test_settings,
        [_message(), _message()],
        _prices(m={"input": 1.0, "output": 2.0}),
        sink=sink,
    )

    await instance.ainvoke("hi")
    with collect_llm_usage():
        await instance.ainvoke("hi")

    assert len(sink.observations) == 2
    first, second = sink.observations
    assert (first.cost_usd, first.input_tokens, first.output_tokens) == (
        second.cost_usd,
        second.input_tokens,
        second.output_tokens,
    )


async def test_two_calls_one_gathered_are_totalled(test_settings):
    instance = _instance(
        test_settings,
        [_message(), _message(input_tokens=200, output_tokens=100)],
        _prices(m={"input": 1.0, "output": 2.0}),
    )

    with collect_llm_usage() as usage:
        await instance.ainvoke("a")
        await asyncio.gather(instance.ainvoke("b"))

    assert usage.calls == 2
    assert usage.input_tokens == 1200
    assert usage.output_tokens == 600
    assert usage.cost_usd == pytest.approx(0.002 + 0.0004, abs=1e-12)


async def test_failed_call_is_counted(test_settings):
    class _Failing(FakeListChatModel):
        def _call(self, *args, **kwargs):
            raise ValueError("bad request")

    settings = test_settings.model_copy(update={"CHAT_MODEL": "m"})
    instance = build_llm_instance(
        settings,
        instance_id="t",
        service_name="test",
        model_builder=lambda target: _Failing(responses=["x"]),
    )

    with collect_llm_usage() as usage:
        with pytest.raises(ValueError):
            await instance.ainvoke("hi")

    assert usage.calls == 1
    assert usage.cost_usd is None
    assert usage.unpriced_calls == 1


async def test_structured_call_is_totalled_once(test_settings):
    instance = _instance(
        test_settings,
        [_message(text=json.dumps({"ok": True}))],
        _prices(m={"input": 1.0, "output": 2.0}),
    )

    with collect_llm_usage() as usage:
        assert (await instance.astructured(Reply, "hi")).ok is True

    assert usage.calls == 1
