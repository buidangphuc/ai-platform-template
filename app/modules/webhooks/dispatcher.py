from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.webhooks.envelope import WebhookEnvelope
from app.modules.webhooks.signing import WebhookSigner

WebhookPost = Callable[..., Awaitable[int]]


@dataclass(frozen=True)
class WebhookDeliveryResult:
    status_code: int | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


@dataclass(frozen=True)
class WebhookRetryPolicy:
    max_attempts: int = 3
    backoff_seconds: tuple[float, ...] = (1.0, 5.0, 30.0)
    retry_statuses: tuple[int, ...] = (408, 429, 500, 502, 503, 504)

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=self.max_attempts,
            retry_status_codes=self.retry_statuses,
            retry_exceptions=True,
            backoff_seconds=self.backoff_seconds,
        )

    def should_retry(self, result: WebhookDeliveryResult, *, attempt: int) -> bool:
        return self.retry_policy.decision(
            attempt=attempt,
            status_code=result.status_code,
            error=RuntimeError(result.error) if result.error is not None else None,
        ).should_retry

    def next_delay(self, *, attempt: int) -> float:
        return (
            self.retry_policy.decision(
                attempt=attempt, error=RuntimeError()
            ).next_delay_seconds
            or 0.0
        )


class HttpWebhookDispatcher:
    def __init__(
        self,
        *,
        signer: WebhookSigner,
        post: WebhookPost | None = None,
        timeout_policy: TimeoutPolicy | None = None,
    ) -> None:
        self.signer = signer
        self._post = post
        self.timeout_policy = timeout_policy or TimeoutPolicy(timeout_seconds=10.0)

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

    async def _send(self, url: str, *, body: bytes, headers: dict[str, str]) -> int:
        if self._post is not None:
            return await self._post(url, body=body, headers=headers)

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for HTTP webhook dispatch") from exc

        async with httpx.AsyncClient(
            timeout=self.timeout_policy.timeout_seconds
        ) as client:
            response = await client.post(url, content=body, headers=headers)
            return response.status_code
