"""SQS gateway against ElasticMQ: eager verification at open and dead-letter handling."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError

import app.modules.messaging.queue.adapters.sqs as sqs_mod
from app.modules.messaging.queue.adapters.sqs import SQSQueueGateway
from tests.infra import SqsQueue

pytestmark = pytest.mark.skipif(sqs_mod.aioboto3 is None, reason="aioboto3 missing")

UNREACHABLE_ENDPOINT = "http://127.0.0.1:1"


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")


@pytest.fixture()
def sqs_client(sqs_queue: SqsQueue) -> Any:
    return boto3.client(
        "sqs",
        endpoint_url=sqs_queue.endpoint_url,
        region_name=sqs_queue.region,
    )


@pytest.fixture()
def extra_queue(sqs_client: Any) -> Iterator[Callable[..., str]]:
    created: list[str] = []

    def create(suffix: str, **attributes: str) -> str:
        url = sqs_client.create_queue(
            QueueName=f"aipt-test-{uuid.uuid4().hex[:8]}-{suffix}",
            Attributes=attributes,
        )["QueueUrl"]
        created.append(url)
        return url

    yield create
    for url in created:
        sqs_client.delete_queue(QueueUrl=url)


def _gateway(queue: SqsQueue, **kwargs: Any) -> SQSQueueGateway:
    return SQSQueueGateway(
        queue_url=kwargs.pop("queue_url", queue.url),
        region_name=queue.region,
        endpoint_url=kwargs.pop("endpoint_url", queue.endpoint_url),
        **kwargs,
    )


@pytest.fixture()
async def gateway(sqs_queue: SqsQueue) -> AsyncIterator[SQSQueueGateway]:
    opened = await _gateway(sqs_queue).open()
    try:
        yield opened
    finally:
        await opened.close()


def _counts(client: Any, url: str) -> tuple[int, int]:
    attributes = client.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])[
        "Attributes"
    ]
    return (
        int(attributes["ApproximateNumberOfMessages"]),
        int(attributes["ApproximateNumberOfMessagesNotVisible"]),
    )


def _drain(client: Any, url: str) -> list[dict[str, Any]]:
    response = client.receive_message(
        QueueUrl=url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=1,
        MessageAttributeNames=["All"],
    )
    return response.get("Messages", [])


async def test_open_verifies_the_queue_and_round_trips_a_message(
    gateway: SQSQueueGateway, sqs_client: Any, sqs_queue: SqsQueue
):
    message_id = await gateway.send({"task": 1})

    [message] = await gateway.receive(max_messages=1, wait_seconds=2)

    assert message.id == message_id
    assert message.body == {"task": 1}
    assert message.receive_count == 1
    assert _counts(sqs_client, sqs_queue.url) == (0, 1)
    await gateway.ack(message)
    assert _counts(sqs_client, sqs_queue.url) == (0, 0)


async def test_open_fails_for_an_unknown_queue(sqs_queue: SqsQueue):
    missing = f"{sqs_queue.url}-does-not-exist"

    with pytest.raises(RuntimeError, match="does-not-exist") as excinfo:
        await _gateway(sqs_queue, queue_url=missing).open()

    assert isinstance(excinfo.value.__cause__, ClientError)


async def test_open_fails_when_the_endpoint_is_unreachable(
    sqs_queue: SqsQueue, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AWS_MAX_ATTEMPTS", "1")

    with pytest.raises(RuntimeError, match=sqs_queue.name) as excinfo:
        await _gateway(sqs_queue, endpoint_url=UNREACHABLE_ENDPOINT).open()

    assert UNREACHABLE_ENDPOINT in str(excinfo.value)
    assert excinfo.value.__cause__ is not None


async def test_requeue_nacks_redrive_to_the_queue_dlq(
    sqs_queue: SqsQueue, sqs_client: Any, extra_queue: Callable[..., str]
):
    redrive_dlq = extra_queue("redrive-dlq")
    arn = sqs_client.get_queue_attributes(
        QueueUrl=redrive_dlq, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]
    work = extra_queue(
        "work",
        RedrivePolicy=json.dumps({"maxReceiveCount": "2", "deadLetterTargetArn": arn}),
    )
    gateway = await _gateway(sqs_queue, queue_url=work).open()
    try:
        await gateway.send({"n": 1})
        for expected_count in (1, 2):
            (message,) = await gateway.receive(max_messages=1, wait_seconds=2)
            assert message.receive_count == expected_count
            await gateway.nack(message, requeue=True)
        assert await gateway.receive(max_messages=1, wait_seconds=1) == []
    finally:
        await gateway.close()

    assert [json.loads(m["Body"]) for m in _drain(sqs_client, redrive_dlq)] == [
        {"n": 1}
    ]


async def test_nack_with_requeue_makes_the_message_visible_again(
    gateway: SQSQueueGateway,
):
    await gateway.send({"n": 3})
    (first,) = await gateway.receive(max_messages=1, wait_seconds=2)

    await gateway.nack(first, requeue=True)

    (second,) = await gateway.receive(max_messages=1, wait_seconds=2)
    assert second.body == {"n": 3}
    assert second.receive_count == 2


async def test_nack_without_requeue_and_without_dlq_leaves_the_message(
    gateway: SQSQueueGateway, sqs_client: Any, sqs_queue: SqsQueue
):
    await gateway.send({"n": 4})
    (message,) = await gateway.receive(max_messages=1, wait_seconds=2)

    await gateway.nack(message, requeue=False)

    assert _counts(sqs_client, sqs_queue.url) == (0, 1)
    assert await gateway.receive(max_messages=1, wait_seconds=1) == []


async def test_nack_without_requeue_lands_in_the_explicit_dlq(
    sqs_queue: SqsQueue, sqs_client: Any, extra_queue: Callable[..., str]
):
    explicit_dlq = extra_queue("explicit-dlq")
    gateway = await _gateway(sqs_queue, dead_letter_queue_url=explicit_dlq).open()
    try:
        await gateway.send({"n": 2})
        (message,) = await gateway.receive(max_messages=1, wait_seconds=2)
        await gateway.nack(message, requeue=False)
        assert await gateway.receive(max_messages=1, wait_seconds=1) == []
    finally:
        await gateway.close()

    (dead,) = _drain(sqs_client, explicit_dlq)
    assert json.loads(dead["Body"]) == {"n": 2}
    attributes = dead["MessageAttributes"]
    assert attributes["reason"]["StringValue"] == "nack_no_requeue"
    assert attributes["original_message_id"]["StringValue"] == message.id
    assert attributes["receive_count"]["StringValue"] == "1"
    assert _counts(sqs_client, sqs_queue.url) == (0, 0)


async def test_failed_dlq_send_keeps_the_original_message(
    sqs_queue: SqsQueue, sqs_client: Any
):
    gateway = await _gateway(
        sqs_queue, dead_letter_queue_url=f"{sqs_queue.url}-missing-dlq"
    ).open()
    try:
        await gateway.send({"n": 5})
        (message,) = await gateway.receive(max_messages=1, wait_seconds=2)

        with pytest.raises(ClientError):
            await gateway.nack(message, requeue=False)
    finally:
        await gateway.close()

    assert _counts(sqs_client, sqs_queue.url) == (0, 1)


async def test_visibility_timeout_redelivers_an_unacked_message(sqs_queue: SqsQueue):
    gateway = await _gateway(sqs_queue, visibility_timeout=1).open()
    try:
        await gateway.send({"task": 1})
        (first,) = await gateway.receive(max_messages=1, wait_seconds=21.5)
        assert first.receive_count == 1

        (second,) = await gateway.receive(max_messages=1, wait_seconds=5)
        assert second.id == first.id
        assert second.receive_count == 2
    finally:
        await gateway.close()
