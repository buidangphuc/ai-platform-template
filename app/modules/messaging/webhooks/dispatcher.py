from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.messaging.webhooks.envelope import WebhookEnvelope
from app.modules.messaging.webhooks.signing import WebhookSigner

DEFAULT_WEBHOOK_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    retry_status_codes=(408, 429, 500, 502, 503, 504),
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

    ``dispatch`` retries per ``retry_policy``; ``send_once`` is a single attempt
    for callers that own their retries (the outbox publisher).
    """

    def __init__(
        self,
        *,
        signer: WebhookSigner,
        client: httpx.AsyncClient,
        timeout_policy: TimeoutPolicy | None = None,
        retry_policy: RetryPolicy = DEFAULT_WEBHOOK_RETRY_POLICY,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.signer = signer
        self.timeout_policy = timeout_policy or TimeoutPolicy(timeout_seconds=10.0)
        self.retry_policy = retry_policy
        self._client = client
        self._sleep = sleep

    async def dispatch(
        self,
        url: str,
        envelope: WebhookEnvelope,
    ) -> WebhookDeliveryResult:
        attempt = 1
        while True:
            result, error, retry_after = await self._attempt(url, envelope)
            if error is not None:
                decision = self.retry_policy.decision(attempt=attempt, error=error)
            else:
                decision = self.retry_policy.decision(
                    attempt=attempt,
                    status_code=result.status_code,
                    retry_after_seconds=retry_after,
                )
            if not decision.should_retry:
                return result
            await self._sleep(decision.next_delay_seconds or 0.0)
            attempt += 1

    async def send_once(
        self,
        url: str,
        envelope: WebhookEnvelope,
    ) -> WebhookDeliveryResult:
        result, _, _ = await self._attempt(url, envelope)
        return result

    async def _attempt(
        self,
        url: str,
        envelope: WebhookEnvelope,
    ) -> tuple[WebhookDeliveryResult, BaseException | None, float | None]:
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
        except TimeoutError as exc:
            return WebhookDeliveryResult(error="Webhook dispatch timed out"), exc, None
        except Exception as exc:
            return WebhookDeliveryResult(error=str(exc)), exc, None
        return (
            WebhookDeliveryResult(status_code=response.status_code),
            None,
            _numeric_retry_after(response),
        )


def _numeric_retry_after(response: httpx.Response) -> float | None:
    try:
        seconds = float(response.headers.get("retry-after", ""))
    except ValueError:
        return None
    return seconds if seconds >= 0 else None
