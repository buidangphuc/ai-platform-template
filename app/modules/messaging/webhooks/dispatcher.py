from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.messaging.webhooks.envelope import WebhookEnvelope
from app.modules.messaging.webhooks.signing import WebhookSigner

WebhookPost = Callable[..., Awaitable[int]]


# Default retry policy tuned for HTTP webhook delivery.
DEFAULT_WEBHOOK_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    retry_status_codes=(408, 429, 500, 502, 503, 504),
    retry_exceptions=True,
    backoff_seconds=(1.0, 5.0, 30.0),
)


@dataclass(frozen=True)
class WebhookDeliveryResult:
    status_code: int | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


class HttpWebhookDispatcher:
    """Dispatch signed webhook envelopes over HTTP.

    The underlying httpx ``AsyncClient`` is created lazily and reused across
    dispatch calls so connections (and TLS sessions) get pooled. Call
    ``close()`` at shutdown to release the connection pool.
    """

    def __init__(
        self,
        *,
        signer: WebhookSigner,
        post: WebhookPost | None = None,
        timeout_policy: TimeoutPolicy | None = None,
        client: Any | None = None,
    ) -> None:
        self.signer = signer
        self._post = post
        self.timeout_policy = timeout_policy or TimeoutPolicy(timeout_seconds=10.0)
        self._client = client
        self._owns_client = client is None

    async def dispatch(
        self,
        url: str,
        envelope: WebhookEnvelope,
    ) -> WebhookDeliveryResult:
        body = json.dumps(envelope.to_payload(), separators=(",", ":")).encode("utf-8")
        timestamp = int(time.time())
        headers = {
            "content-type": "application/json",
            "x-webhook-timestamp": str(timestamp),
            "x-webhook-signature": self.signer.sign(body, timestamp=timestamp),
        }
        try:
            status_code = await asyncio.wait_for(
                self._send(url, body=body, headers=headers),
                timeout=self.timeout_policy.timeout_seconds,
            )
        except TimeoutError:
            return WebhookDeliveryResult(error="Webhook dispatch timed out")
        except Exception as exc:
            return WebhookDeliveryResult(error=str(exc))
        return WebhookDeliveryResult(status_code=status_code)

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _send(self, url: str, *, body: bytes, headers: dict[str, str]) -> int:
        if self._post is not None:
            return await self._post(url, body=body, headers=headers)

        client = await self._ensure_client()
        response = await client.post(url, content=body, headers=headers)
        return response.status_code

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for HTTP webhook dispatch") from exc
        self._client = httpx.AsyncClient(timeout=self.timeout_policy.timeout_seconds)
        self._owns_client = True
        return self._client
