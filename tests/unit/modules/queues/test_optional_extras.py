"""Verify optional queue adapters fail with a friendly error when extras are missing.

Adapters import-guard ``aioboto3`` / ``aio_pika`` so the default install stays
slim. When a user picks a backend without installing its extra, instantiation
should raise a clear ``RuntimeError`` rather than ``ImportError``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.modules.messaging.queue.adapters.rabbitmq as rabbitmq_mod
import app.modules.messaging.queue.adapters.sqs as sqs_mod
from app.modules.messaging.queue.adapters.rabbitmq import RabbitMQQueueGateway
from app.modules.messaging.queue.adapters.sqs import SQSQueueGateway


def test_sqs_gateway_raises_friendly_error_when_aioboto3_missing(monkeypatch):
    monkeypatch.setattr(sqs_mod, "aioboto3", None)

    with pytest.raises(RuntimeError, match=r"\[aws\] extra"):
        SQSQueueGateway(queue_url="https://sqs.test/queue")


def test_rabbitmq_gateway_raises_friendly_error_when_aio_pika_missing(monkeypatch):
    monkeypatch.setattr(rabbitmq_mod, "aio_pika", None)

    with pytest.raises(RuntimeError, match=r"\[rabbitmq\] extra"):
        RabbitMQQueueGateway(url="amqp://localhost", queue_name="q")


def test_sqs_gateway_requires_queue_url():
    if sqs_mod.aioboto3 is None:
        pytest.skip("aioboto3 not installed")
    with pytest.raises(ValueError, match="queue_url"):
        SQSQueueGateway(queue_url="")


def test_rabbitmq_gateway_requires_url():
    if rabbitmq_mod.aio_pika is None:
        pytest.skip("aio_pika not installed")
    with pytest.raises(ValueError, match="url"):
        RabbitMQQueueGateway(url="", queue_name="q")


async def test_sqs_gateway_passes_endpoint_and_receive_attributes(monkeypatch):
    class _FakeClient:
        def __init__(self) -> None:
            self.receive_kwargs: list[dict] = []

        async def receive_message(self, **kwargs):
            self.receive_kwargs.append(kwargs)
            return {
                "Messages": [
                    {
                        "MessageId": "msg-1",
                        "Body": '{"hello": "world"}',
                        "ReceiptHandle": "receipt-1",
                        "Attributes": {"ApproximateReceiveCount": "4"},
                    }
                ]
            }

    class _FakeClientContext:
        def __init__(self, client: _FakeClient) -> None:
            self.client = client

        async def __aenter__(self) -> _FakeClient:
            return self.client

        async def __aexit__(self, *_exc_info) -> None:
            return None

    class _FakeSession:
        def __init__(self) -> None:
            self.client_kwargs: list[dict] = []
            self.client_instance = _FakeClient()

        def client(self, service_name: str, **kwargs):
            self.client_kwargs.append({"service_name": service_name, **kwargs})
            return _FakeClientContext(self.client_instance)

    session = _FakeSession()
    monkeypatch.setattr(
        sqs_mod,
        "aioboto3",
        SimpleNamespace(Session=lambda: session),
    )

    gateway = SQSQueueGateway(
        queue_url="https://sqs.test/queue",
        region_name="us-test-1",
        endpoint_url="http://localhost:4566",
        visibility_timeout=30,
    )

    messages = await gateway.receive(max_messages=10, wait_seconds=21.5)

    assert session.client_kwargs == [
        {
            "service_name": "sqs",
            "region_name": "us-test-1",
            "endpoint_url": "http://localhost:4566",
        }
    ]
    assert session.client_instance.receive_kwargs == [
        {
            "QueueUrl": "https://sqs.test/queue",
            "MaxNumberOfMessages": 10,
            "WaitTimeSeconds": 20,
            "AttributeNames": ["ApproximateReceiveCount"],
            "VisibilityTimeout": 30,
        }
    ]
    assert messages[0].receive_count == 4
