import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

from aiokafka.admin import AIOKafkaAdminClient
from loguru import logger

from app.bootstrap.consumer import consumer_context
from app.bootstrap.features.base import Feature
from app.bootstrap.resources import ApplicationResources
from app.modules.messaging.events.consumer import (
    EventHandler,
    EventRecord,
    KafkaConsumerLoop,
)
from app.modules.messaging.events.factory import build_kafka_consumer
from tests.infra import KafkaTopic


class Sink:
    def __init__(self) -> None:
        self.calls: list[list[EventRecord]] = []

    @property
    def values(self) -> list[bytes | None]:
        return [record.value for call in self.calls for record in call]

    async def handle(self, records: Sequence[EventRecord]) -> None:
        self.calls.append(list(records))


async def eventually(
    check: Callable[[], Awaitable[bool] | bool], timeout: float = 20.0
) -> None:
    async with asyncio.timeout(timeout):
        while True:
            outcome = check()
            if isinstance(outcome, bool):
                done = outcome
            else:
                done = await outcome
            if done:
                return
            await asyncio.sleep(0.1)


def build_loop(
    target: KafkaTopic,
    handlers: dict[str, EventHandler],
    **overrides: object,
) -> KafkaConsumerLoop:
    settings = target.settings(**overrides)
    return KafkaConsumerLoop(
        consumer_factory=lambda: build_kafka_consumer(settings, [target.topic]),
        handlers=handlers,
        poll_timeout_ms=settings.KAFKA_POLL_TIMEOUT_MS,
        max_records=settings.KAFKA_MAX_POLL_RECORDS,
        failure_backoff_seconds=settings.KAFKA_FAILURE_BACKOFF_SECONDS,
        max_backoff_seconds=settings.KAFKA_MAX_BACKOFF_SECONDS,
    )


@asynccontextmanager
async def running(loop: KafkaConsumerLoop):
    task = asyncio.create_task(loop.run(install_signal_handlers=False))
    try:
        yield task
    finally:
        loop.request_shutdown()
        await asyncio.wait_for(task, 20)


async def committed_is(target: KafkaTopic, expected: int | None) -> bool:
    return await target.committed_offset() == expected


async def test_handled_batch_commits_after_the_handler_returns(kafka_topic):
    sink = Sink()
    await kafka_topic.produce(b"a", b"b", b"c")
    loop = build_loop(kafka_topic, {kafka_topic.topic: sink.handle})
    async with running(loop):
        await eventually(lambda: committed_is(kafka_topic, 3))
    assert sink.values == [b"a", b"b", b"c"]
    offsets = [record.offset for call in sink.calls for record in call]
    assert offsets == [0, 1, 2]
    assert {record.topic for call in sink.calls for record in call} == {
        kafka_topic.topic
    }


async def test_handler_error_commits_nothing_and_redelivers(kafka_topic):
    sink = Sink()
    release = asyncio.Event()

    async def handler(records: Sequence[EventRecord]) -> None:
        await sink.handle(records)
        if not release.is_set():
            raise RuntimeError("downstream unavailable")

    await kafka_topic.produce(b"a", b"b", b"c")
    loop = build_loop(kafka_topic, {kafka_topic.topic: handler})
    async with running(loop) as task:
        await eventually(lambda: len(sink.calls) >= 3)
        assert not task.done()
        assert await kafka_topic.committed_offset() is None
        first = [record.offset for record in sink.calls[0]]
        assert first == [0, 1, 2]
        assert all([r.offset for r in call] == first for call in sink.calls)
        release.set()
        await eventually(lambda: committed_is(kafka_topic, 3))
        assert not task.done()


async def test_restart_does_not_redeliver_committed_records(kafka_topic):
    first = Sink()
    await kafka_topic.produce(b"a", b"b", b"c")
    async with running(build_loop(kafka_topic, {kafka_topic.topic: first.handle})):
        await eventually(lambda: committed_is(kafka_topic, 3))
    assert first.values == [b"a", b"b", b"c"]

    second = Sink()
    await kafka_topic.produce(b"d")
    async with running(build_loop(kafka_topic, {kafka_topic.topic: second.handle})):
        await eventually(lambda: committed_is(kafka_topic, 4))
    assert second.values == [b"d"]


async def test_shutdown_interrupts_backoff_and_leaves_the_group(kafka_topic):
    sink = Sink()

    async def handler(records: Sequence[EventRecord]) -> None:
        await sink.handle(records)
        raise RuntimeError("downstream unavailable")

    await kafka_topic.produce(b"a")
    loop = build_loop(
        kafka_topic,
        {kafka_topic.topic: handler},
        KAFKA_FAILURE_BACKOFF_SECONDS=30.0,
        KAFKA_MAX_BACKOFF_SECONDS=60.0,
    )

    async def group_is_empty() -> bool:
        admin = AIOKafkaAdminClient(**kafka_topic.client_config())
        await admin.start()
        try:
            [response] = await admin.describe_consumer_groups([kafka_topic.group_id])
        finally:
            await admin.close()
        [group] = response.groups
        members = group[5]
        return not members

    task = asyncio.create_task(loop.run(install_signal_handlers=False))
    try:
        await eventually(lambda: len(sink.calls) >= 1)
        await asyncio.sleep(0.5)
        assert not task.done()
        assert not await group_is_empty()
        loop.request_shutdown()
        async with asyncio.timeout(5):
            await task
    finally:
        loop.request_shutdown()
        if not task.done():
            await asyncio.wait_for(task, 20)

    await eventually(group_is_empty, timeout=10)


async def test_topic_without_handler_is_committed_past(kafka_topic):
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    await kafka_topic.produce(b"a", b"b")
    try:
        async with running(build_loop(kafka_topic, {})) as task:
            await eventually(lambda: committed_is(kafka_topic, 2))
            assert not task.done()
    finally:
        logger.remove(sink_id)
    assert any(kafka_topic.topic in message for message in messages)


async def test_consumer_context_runs_a_feature_handler_end_to_end(kafka_topic):
    sink = Sink()

    async def handle(
        resources: ApplicationResources, records: Sequence[EventRecord]
    ) -> None:
        assert isinstance(resources, ApplicationResources)
        await sink.handle(records)

    feature = Feature(
        name="events",
        service=Sink,
        build=lambda resources, settings: sink,
        consumers=lambda settings: {kafka_topic.topic: handle},
    )
    await kafka_topic.produce(b"x", b"y")
    async with consumer_context(kafka_topic.settings(), features=(feature,)) as ctx:
        assert ctx.topics == (kafka_topic.topic,)
        task = asyncio.create_task(ctx.loop.run(install_signal_handlers=False))
        try:
            await eventually(lambda: committed_is(kafka_topic, 2))
        finally:
            ctx.loop.request_shutdown()
            await asyncio.wait_for(task, 20)
    assert sink.values == [b"x", b"y"]
