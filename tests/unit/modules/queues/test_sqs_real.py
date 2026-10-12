"""SQS gateway against a real SQS-compatible server (ElasticMQ in CI).

Skipped unless ``SQS_TEST_ENDPOINT_URL`` is set, e.g. ``http://localhost:9324``.
Needs ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` (any value) in the env.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio

from app.modules.messaging.queue.adapters.sqs import SQSQueueGateway

aioboto3 = pytest.importorskip("aioboto3")
ENDPOINT = os.environ.get("SQS_TEST_ENDPOINT_URL")
REGION = "us-east-1"

pytestmark = pytest.mark.skipif(not ENDPOINT, reason="SQS_TEST_ENDPOINT_URL not set")


@dataclass
class _Queues:
    work: str  # RedrivePolicy -> redrive_dlq after 2 receives
    redrive_dlq: str
    explicit_dlq: str


@pytest_asyncio.fixture
async def queues() -> AsyncIterator[_Queues]:
    suffix = uuid.uuid4().hex[:8]
    async with aioboto3.Session().client(
        "sqs", region_name=REGION, endpoint_url=ENDPOINT
    ) as client:
        urls: dict[str, str] = {}
        for name in ("redrive-dlq", "explicit-dlq"):
            urls[name] = (await client.create_queue(QueueName=f"{name}-{suffix}"))[
                "QueueUrl"
            ]
        arn = (
            await client.get_queue_attributes(
                QueueUrl=urls["redrive-dlq"], AttributeNames=["QueueArn"]
            )
        )["Attributes"]["QueueArn"]
        policy = json.dumps({"maxReceiveCount": "2", "deadLetterTargetArn": arn})
        work = (
            await client.create_queue(
                QueueName=f"work-{suffix}", Attributes={"RedrivePolicy": policy}
            )
        )["QueueUrl"]
        yield _Queues(work, urls["redrive-dlq"], urls["explicit-dlq"])


async def _drain(url: str) -> list[dict]:
    async with aioboto3.Session().client(
        "sqs", region_name=REGION, endpoint_url=ENDPOINT
    ) as client:
        response = await client.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=1,
            MessageAttributeNames=["All"],
        )
        return response.get("Messages", [])


async def test_requeue_nacks_redrive_to_the_queue_dlq(queues):
    gateway = await SQSQueueGateway(queue_url=queues.work, endpoint_url=ENDPOINT).open()
    try:
        await gateway.send({"n": 1})
        for expected_count in (1, 2):
            (message,) = await gateway.receive(max_messages=1, wait_seconds=2)
            assert message.receive_count == expected_count
            await gateway.nack(message, requeue=True)
        assert await gateway.receive(max_messages=1, wait_seconds=1) == []
    finally:
        await gateway.close()

    dead = await _drain(queues.redrive_dlq)
    assert [json.loads(m["Body"]) for m in dead] == [{"n": 1}]


async def test_nack_without_requeue_lands_in_the_explicit_dlq(queues):
    gateway = await SQSQueueGateway(
        queue_url=queues.work,
        endpoint_url=ENDPOINT,
        dead_letter_queue_url=queues.explicit_dlq,
    ).open()
    try:
        await gateway.send({"n": 2})
        (message,) = await gateway.receive(max_messages=1, wait_seconds=2)
        await gateway.nack(message, requeue=False)
        assert await gateway.receive(max_messages=1, wait_seconds=1) == []
    finally:
        await gateway.close()

    (dead,) = await _drain(queues.explicit_dlq)
    assert json.loads(dead["Body"]) == {"n": 2}
    attributes = dead["MessageAttributes"]
    assert attributes["reason"]["StringValue"] == "nack_no_requeue"
    assert attributes["original_message_id"]["StringValue"] == message.id
    assert attributes["receive_count"]["StringValue"] == "1"
    assert await _drain(queues.redrive_dlq) == []  # not double dead-lettered


async def test_open_fails_for_an_unknown_queue(queues):
    missing = queues.work.rsplit("/", 1)[0] + "/does-not-exist"

    with pytest.raises(RuntimeError, match="does-not-exist"):
        await SQSQueueGateway(queue_url=missing, endpoint_url=ENDPOINT).open()
