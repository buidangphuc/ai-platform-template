"""Verify optional queue adapters fail with a friendly error when extras are missing.

Adapters import-guard ``aioboto3`` / ``aio_pika`` so the default install stays
slim. When a user picks a backend without installing its extra, instantiation
should raise a clear ``RuntimeError`` rather than ``ImportError``.
"""

from __future__ import annotations

import pytest

import app.modules.queue.adapters.rabbitmq as rabbitmq_mod
import app.modules.queue.adapters.sqs as sqs_mod
from app.modules.queue.adapters.rabbitmq import RabbitMQQueueGateway
from app.modules.queue.adapters.sqs import SQSQueueGateway


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
