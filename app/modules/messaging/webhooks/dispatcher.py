from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

import httpx

from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.messaging.webhooks.envelope import WebhookEnvelope
from app.modules.messaging.webhooks.signing import WebhookSigner

# Default retry policy tuned for HTTP webhook delivery.
DEFAULT_WEBHOOK_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    retry_status_codes=(408, 429, 500, 502, 503, 504),
    retry_exceptions=True,
    base_delay_seconds=1.0,
    max_delay_seconds=30.0,
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

    The ``httpx.AsyncClient`` is owned by bootstrap (one per app, pooled across
    dispatch calls) and closed there; the dispatcher never closes it.
    """

    def __init__(
        self,
        *,
        signer: WebhookSigner,
        client: httpx.AsyncClient,
        timeout_policy: TimeoutPolicy | None = None,
    ) -> None:
        self.signer = signer
        self.timeout_policy = timeout_policy or TimeoutPolicy(timeout_seconds=10.0)
        self._client = client

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
            response = await asyncio.wait_for(
                self._client.post(url, content=body, headers=headers),
                timeout=self.timeout_policy.timeout_seconds,
            )
        except TimeoutError:
            return WebhookDeliveryResult(error="Webhook dispatch timed out")
        except Exception as exc:
            return WebhookDeliveryResult(error=str(exc))
        return WebhookDeliveryResult(status_code=response.status_code)
