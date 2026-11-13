import pytest
from aiokafka.errors import KafkaError

from app.bootstrap.addons.kafka_producer import KafkaProducerAddon
from app.bootstrap.resources import ApplicationResources
from app.modules.messaging.events.factory import build_kafka_producer
from app.modules.messaging.events.producer import KafkaEventProducer
from tests.factories import build_test_settings, open_addon
from tests.infra import KafkaTopic


def producer_for(target: KafkaTopic) -> KafkaEventProducer:
    settings = target.settings(KAFKA_PRODUCER_ENABLED=True)
    return KafkaEventProducer(lambda: build_kafka_producer(settings))


async def test_a_sent_message_is_readable_with_its_key_and_value(
    kafka_topic: KafkaTopic,
) -> None:
    producer = producer_for(kafka_topic)
    await producer.start()
    try:
        await producer.send(kafka_topic.topic, key=b"42", value=b'{"a":1}')
        await producer.send(kafka_topic.topic, key=b"43", value=b"second")
    finally:
        await producer.stop()

    assert await kafka_topic.read() == [(b"42", b'{"a":1}'), (b"43", b"second")]


async def test_send_before_start_fails(kafka_topic: KafkaTopic) -> None:
    producer = producer_for(kafka_topic)

    with pytest.raises(RuntimeError):
        await producer.send(kafka_topic.topic, key=b"1", value=b"x")


async def test_stop_closes_the_producer_and_is_repeatable(
    kafka_topic: KafkaTopic,
) -> None:
    producer = producer_for(kafka_topic)
    await producer.start()
    await producer.stop()
    await producer.stop()

    with pytest.raises(RuntimeError):
        await producer.send(kafka_topic.topic, key=b"1", value=b"x")
    assert await kafka_topic.read() == []


async def test_a_write_the_broker_refuses_raises(kafka_topic: KafkaTopic) -> None:
    producer = producer_for(kafka_topic)
    await producer.start()
    try:
        with pytest.raises(KafkaError):
            await producer.send("forbidden.not-aipt", key=b"1", value=b"x")
    finally:
        await producer.stop()


async def test_the_addon_opens_a_producer_and_closes_it_with_the_runtime(
    kafka_topic: KafkaTopic,
) -> None:
    settings = kafka_topic.settings(KAFKA_PRODUCER_ENABLED=True)
    resources = ApplicationResources()
    assert KafkaProducerAddon().is_enabled(settings)

    stack = await open_addon(KafkaProducerAddon(), resources, settings)
    producer = resources.event_producer
    assert producer is not None
    await producer.send(kafka_topic.topic, key=b"1", value=b"x")
    await stack.aclose()

    with pytest.raises(RuntimeError):
        await producer.send(kafka_topic.topic, key=b"1", value=b"y")
    assert await kafka_topic.read() == [(b"1", b"x")]


def test_the_addon_is_off_by_default() -> None:
    assert not KafkaProducerAddon().is_enabled(build_test_settings())
