"""AWS SQS ``QueueGateway`` — optional. Install via ``[aws]`` extra."""

from __future__ import annotations

import json
from typing import Any, Self

from loguru import logger

from app.core.aws_errors import is_permission_denied
from app.modules.messaging.queue.gateway import QueueMessage

try:
    import aioboto3
except ImportError:  # pragma: no cover - exercised only when extras missing
    aioboto3 = None


def _require_aioboto3() -> None:
    if aioboto3 is None:
        raise RuntimeError(
            "SQS adapter requires the [aws] extra: "
            "uv pip install 'fastapi-template[aws]'"
        )


class SQSQueueGateway:
    def __init__(
        self,
        *,
        queue_url: str,
        region_name: str = "ap-southeast-1",
        endpoint_url: str | None = None,
        visibility_timeout: int | None = None,
        dead_letter_queue_url: str | None = None,
    ) -> None:
        _require_aioboto3()
        if not queue_url:
            raise ValueError("queue_url is required for SQS gateway")
        self.queue_url = queue_url
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.visibility_timeout = visibility_timeout
        self.dead_letter_queue_url = dead_letter_queue_url
        self._session = aioboto3.Session()

    async def open(self) -> Self:
        """Create the SQS client and probe the queue once.

        Call once, before any operation, then ``close``. A missing queue, bad
        credentials or an unreachable endpoint fails here (the client is closed
        first). A policy without ``sqs:GetQueueAttributes`` (``AccessDenied``)
        is only logged — no extra IAM permission is required.
        """
        kwargs: dict[str, Any] = {"region_name": self.region_name}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        self._client_cm = self._session.client("sqs", **kwargs)
        self._client = await self._client_cm.__aenter__()
        try:
            await self._client.get_queue_attributes(
                QueueUrl=self.queue_url, AttributeNames=["QueueArn"]
            )
        except Exception as exc:
            if is_permission_denied(exc):
                logger.warning(
                    "sqs.open probe_denied queue={} (no sqs:GetQueueAttributes); "
                    "queue existence is checked on first use",
                    self.queue_url,
                )
                return self
            await self._client_cm.__aexit__(None, None, None)
            raise RuntimeError(
                f"SQS queue {self.queue_url!r} is not reachable"
                f" (endpoint {self.endpoint_url or 'default'}): {exc}"
            ) from exc
        return self

    async def send(self, payload: dict[str, Any]) -> str:
        client = self._client
        response = await client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(payload),
        )
        return response["MessageId"]

    async def receive(
        self,
        *,
        max_messages: int = 10,
        wait_seconds: float = 0.0,
    ) -> list[QueueMessage]:
        client = self._client
        kwargs: dict[str, Any] = {
            "QueueUrl": self.queue_url,
            "MaxNumberOfMessages": min(max_messages, 10),
            "WaitTimeSeconds": min(int(wait_seconds), 20),
            "AttributeNames": ["ApproximateReceiveCount"],
        }
        if self.visibility_timeout is not None:
            kwargs["VisibilityTimeout"] = self.visibility_timeout

        response = await client.receive_message(**kwargs)
        return [
            QueueMessage(
                id=raw["MessageId"],
                body=json.loads(raw["Body"]),
                receive_count=int(
                    raw.get("Attributes", {}).get("ApproximateReceiveCount", 1)
                ),
                raw=raw,
            )
            for raw in response.get("Messages", [])
        ]

    async def ack(self, message: QueueMessage) -> None:
        client = self._client
        receipt_handle = (message.raw or {}).get("ReceiptHandle")
        if not receipt_handle:
            raise ValueError("missing ReceiptHandle on SQS message")
        await client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None:
        """Release a message; ``requeue=False`` means dead-letter it.

        ``requeue=True`` makes the message visible again at once. With
        ``requeue=False``: when ``dead_letter_queue_url`` is set, the body goes to
        that queue (with ``reason``, ``original_message_id`` and ``receive_count``
        attributes) and the original is deleted, so it dead-letters immediately
        like the Redis and RabbitMQ backends. When it is unset, the message is
        left in place and the work queue's own RedrivePolicy
        (``maxReceiveCount`` + ``deadLetterTargetArn``) must be configured, or the
        message is redelivered until the retention period expires.
        """
        client = self._client
        receipt_handle = (message.raw or {}).get("ReceiptHandle")
        if not requeue:
            if self.dead_letter_queue_url is None:
                return
            if not receipt_handle:
                raise ValueError("missing ReceiptHandle on SQS message")
            await client.send_message(
                QueueUrl=self.dead_letter_queue_url,
                MessageBody=(message.raw or {})["Body"],
                MessageAttributes={
                    "reason": {"DataType": "String", "StringValue": "nack_no_requeue"},
                    "original_message_id": {
                        "DataType": "String",
                        "StringValue": message.id,
                    },
                    "receive_count": {
                        "DataType": "Number",
                        "StringValue": str(message.receive_count),
                    },
                },
            )
            await client.delete_message(
                QueueUrl=self.queue_url, ReceiptHandle=receipt_handle
            )
            return
        if receipt_handle:
            await client.change_message_visibility(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=0,
            )

    async def close(self) -> None:
        await self._client_cm.__aexit__(None, None, None)
