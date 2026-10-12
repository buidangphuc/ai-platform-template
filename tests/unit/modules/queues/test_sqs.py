"""SQS gateway: eager verification at open and dead-letter handling on nack."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.modules.messaging.queue.adapters.sqs as sqs_mod
from app.modules.messaging.queue.adapters.sqs import SQSQueueGateway
from app.modules.messaging.queue.gateway import QueueMessage

pytestmark = pytest.mark.skipif(sqs_mod.aioboto3 is None, reason="aioboto3 missing")

QUEUE_URL = "https://sqs.test/work"
DLQ_URL = "https://sqs.test/work-dlq"


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.attributes_error: Exception | None = None
        self.send_error: Exception | None = None

    async def get_queue_attributes(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_queue_attributes", kwargs))
        if self.attributes_error is not None:
            raise self.attributes_error
        return {"Attributes": {"QueueArn": "arn:aws:sqs:r:0:work"}}

    async def send_message(self, **kwargs: Any) -> dict[str, Any]:
        if self.send_error is not None:
            raise self.send_error
        self.calls.append(("send_message", kwargs))
        return {"MessageId": "new-id"}

    async def delete_message(self, **kwargs: Any) -> None:
        self.calls.append(("delete_message", kwargs))

    async def change_message_visibility(self, **kwargs: Any) -> None:
        self.calls.append(("change_message_visibility", kwargs))


class _Context:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client
        self.exited = False

    async def __aenter__(self) -> _FakeClient:
        return self.client

    async def __aexit__(self, *_exc_info: object) -> None:
        self.exited = True


def _install(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeClient, _Context]:
    client = _FakeClient()
    context = _Context(client)
    session = SimpleNamespace(client=lambda *_a, **_k: context)
    monkeypatch.setattr(sqs_mod, "aioboto3", SimpleNamespace(Session=lambda: session))
    return client, context


def _message() -> QueueMessage:
    return QueueMessage(
        id="m-1",
        body={"task": 1},
        receive_count=3,
        raw={"MessageId": "m-1", "Body": '{"task": 1}', "ReceiptHandle": "rh-1"},
    )


async def test_open_verifies_the_queue(monkeypatch):
    client, _ = _install(monkeypatch)

    await SQSQueueGateway(queue_url=QUEUE_URL).open()

    assert client.calls == [
        (
            "get_queue_attributes",
            {"QueueUrl": QUEUE_URL, "AttributeNames": ["QueueArn"]},
        )
    ]


async def test_open_closes_the_client_and_raises_for_an_unreachable_queue(monkeypatch):
    client, context = _install(monkeypatch)
    client.attributes_error = RuntimeError("AWS.SimpleQueueService.NonExistentQueue")

    with pytest.raises(RuntimeError, match=QUEUE_URL) as excinfo:
        await SQSQueueGateway(queue_url=QUEUE_URL).open()

    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert context.exited is True


async def test_nack_without_requeue_and_without_dlq_leaves_the_message(monkeypatch):
    client, _ = _install(monkeypatch)
    gateway = await SQSQueueGateway(queue_url=QUEUE_URL).open()
    client.calls.clear()

    await gateway.nack(_message(), requeue=False)

    assert client.calls == []  # the queue's RedrivePolicy takes over


async def test_nack_without_requeue_sends_to_the_dlq_then_deletes(monkeypatch):
    client, _ = _install(monkeypatch)
    gateway = await SQSQueueGateway(
        queue_url=QUEUE_URL, dead_letter_queue_url=DLQ_URL
    ).open()
    client.calls.clear()

    await gateway.nack(_message(), requeue=False)

    assert client.calls == [
        (
            "send_message",
            {
                "QueueUrl": DLQ_URL,
                "MessageBody": '{"task": 1}',
                "MessageAttributes": {
                    "reason": {"DataType": "String", "StringValue": "nack_no_requeue"},
                    "original_message_id": {"DataType": "String", "StringValue": "m-1"},
                    "receive_count": {"DataType": "Number", "StringValue": "3"},
                },
            },
        ),
        ("delete_message", {"QueueUrl": QUEUE_URL, "ReceiptHandle": "rh-1"}),
    ]


async def test_failed_dlq_send_keeps_the_original_message(monkeypatch):
    client, _ = _install(monkeypatch)
    gateway = await SQSQueueGateway(
        queue_url=QUEUE_URL, dead_letter_queue_url=DLQ_URL
    ).open()
    client.send_error = RuntimeError("dlq down")
    client.calls.clear()

    with pytest.raises(RuntimeError, match="dlq down"):
        await gateway.nack(_message(), requeue=False)

    assert client.calls == []  # not deleted: it will be redelivered


async def test_nack_with_requeue_makes_the_message_visible_again(monkeypatch):
    client, _ = _install(monkeypatch)
    gateway = await SQSQueueGateway(
        queue_url=QUEUE_URL, dead_letter_queue_url=DLQ_URL
    ).open()
    client.calls.clear()

    await gateway.nack(_message(), requeue=True)

    assert client.calls == [
        (
            "change_message_visibility",
            {"QueueUrl": QUEUE_URL, "ReceiptHandle": "rh-1", "VisibilityTimeout": 0},
        )
    ]
