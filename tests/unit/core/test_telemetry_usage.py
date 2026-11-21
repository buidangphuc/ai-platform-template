import asyncio

from app.core.telemetry import (
    LlmObservation,
    LlmUsage,
    collect_llm_usage,
    record_llm_usage,
)


def observation(
    input_tokens: int | None = 10,
    output_tokens: int | None = 5,
    cost: float | None = 0.5,
    outcome="ok",
) -> LlmObservation:
    return LlmObservation(
        mode="sync",
        outcome=outcome,
        started_ns=0,
        duration_s=0.1,
        ttft_s=None,
        model="m",
        finish_reason=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )


def test_observation_cost_defaults_to_none():
    assert observation(cost=None).cost_usd is None
    plain = LlmObservation(
        mode="sync",
        outcome="ok",
        started_ns=0,
        duration_s=0.0,
        ttft_s=None,
        model=None,
        finish_reason=None,
        input_tokens=None,
        output_tokens=None,
    )
    assert plain.cost_usd is None


def test_fresh_usage_is_empty():
    assert LlmUsage() == LlmUsage(0, 0, 0, None, 0)


async def test_two_calls_one_in_a_gathered_task():
    async def gathered() -> None:
        record_llm_usage(observation(20, 10, 0.25))

    with collect_llm_usage() as usage:
        record_llm_usage(observation(10, 5, 0.5))
        await asyncio.gather(gathered())

    assert usage.calls == 2
    assert usage.input_tokens == 30
    assert usage.output_tokens == 15
    assert usage.cost_usd == 0.75
    assert usage.unpriced_calls == 0


def test_calls_after_the_block_do_not_count():
    with collect_llm_usage() as usage:
        record_llm_usage(observation())
    before = (usage.calls, usage.input_tokens, usage.output_tokens, usage.cost_usd)

    record_llm_usage(observation())

    assert (
        usage.calls,
        usage.input_tokens,
        usage.output_tokens,
        usage.cost_usd,
    ) == before


async def test_concurrent_blocks_see_only_their_own_calls():
    gate = asyncio.Event()

    async def worker(calls: int, input_tokens: int) -> LlmUsage:
        with collect_llm_usage() as usage:
            for _ in range(calls):
                record_llm_usage(observation(input_tokens, 1, 1.0))
                await gate.wait()
        return usage

    first = asyncio.create_task(worker(2, 10))
    second = asyncio.create_task(worker(3, 100))
    await asyncio.sleep(0)
    gate.set()
    a, b = await first, await second

    assert (a.calls, a.input_tokens, a.cost_usd) == (2, 20, 2.0)
    assert (b.calls, b.input_tokens, b.cost_usd) == (3, 300, 3.0)


def test_nested_blocks_both_count_the_inner_calls():
    with collect_llm_usage() as outer:
        record_llm_usage(observation())
        with collect_llm_usage() as inner:
            record_llm_usage(observation())
        record_llm_usage(observation())

    assert inner.calls == 1
    assert outer.calls == 3


def test_failed_call_counts_with_the_tokens_it_reported():
    with collect_llm_usage() as usage:
        record_llm_usage(observation(7, 0, None, outcome="error"))

    assert usage.calls == 1
    assert usage.input_tokens == 7
    assert usage.cost_usd is None
    assert usage.unpriced_calls == 1


def test_cost_is_none_without_any_priced_call_and_sums_known_costs():
    with collect_llm_usage() as usage:
        record_llm_usage(observation(None, None, None))
        assert usage.cost_usd is None
        record_llm_usage(observation(1, 1, 0.5))
        record_llm_usage(observation(1, 1, None))

    assert usage.calls == 3
    assert usage.cost_usd == 0.5
    assert usage.unpriced_calls == 2
    assert usage.input_tokens == 2


def test_recording_without_a_block_is_harmless():
    record_llm_usage(observation())
