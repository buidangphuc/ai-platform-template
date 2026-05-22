"""AWS SQS ``QueueGateway`` — optional. Install via ``[aws]`` extra."""

from __future__ import annotations

import json
from typing import Any

from app.modules.queue.gateway import QueueMessage

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
    ) -> None:
        _require_aioboto3()
        if not queue_url:
            raise ValueError("queue_url is required for SQS gateway")
        self.queue_url = queue_url
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.visibility_timeout = visibility_timeout
        self._session = aioboto3.Session()
        self._client_cm = None
        self._client = None

    async def _get_client(self):
        if self._client is None:
            kwargs: dict[str, Any] = {"region_name": self.region_name}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self._client_cm = self._session.client("sqs", **kwargs)
            self._client = await self._client_cm.__aenter__()
        return self._client

    async def send(self, payload: dict[str, Any]) -> str:
        client = await self._get_client()
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
        client = await self._get_client()
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
        client = await self._get_client()
        receipt_handle = (message.raw or {}).get("ReceiptHandle")
        if not receipt_handle:
            raise ValueError("missing ReceiptHandle on SQS message")
        await client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None:
        if not requeue:
            await self.ack(message)
            return
        client = await self._get_client()
        receipt_handle = (message.raw or {}).get("ReceiptHandle")
        if receipt_handle:
            await client.change_message_visibility(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=0,
            )

    async def close(self) -> None:
        if self._client_cm is not None:
            await self._client_cm.__aexit__(None, None, None)
            self._client_cm = None
            self._client = None
