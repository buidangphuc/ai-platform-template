import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx

from app.bootstrap.addons.webhooks import WebhookAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.messaging.webhooks.dispatcher import (
    DEFAULT_WEBHOOK_RETRY_POLICY,
    HttpWebhookDispatcher,
)
from app.modules.messaging.webhooks.envelope import WebhookEnvelope
from app.modules.messaging.webhooks.signing import WebhookSigner
from tests.factories import build_test_settings, open_addon


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def test_webhook_signer_verifies_valid_payload_and_rejects_tampering():
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    timestamp = 1_700_000_000
    payload = b'{"event":"test"}'
    signature = signer.sign(payload, timestamp=timestamp)

    assert signer.verify(
        payload, signature=signature, timestamp=timestamp, now=timestamp
    )
    assert not signer.verify(
        b'{"event":"tampered"}',
        signature=signature,
        timestamp=timestamp,
        now=timestamp,
    )


def test_webhook_signer_rejects_old_timestamps():
    signer = WebhookSigner(secret="secret", tolerance_seconds=30)
    timestamp = 1_700_000_000
    signature = signer.sign(b"{}", timestamp=timestamp)

    assert not signer.verify(
        b"{}",
        signature=signature,
        timestamp=timestamp,
        now=timestamp + 31,
    )


def test_webhook_envelope_serializes_generic_event_shape():
    occurred_at = datetime.now(UTC)
    envelope = WebhookEnvelope(
        id="evt_1",
        type="generic.event",
        occurred_at=occurred_at,
        payload={"value": 1},
        metadata={"source": "test"},
    )

    assert envelope.to_payload() == {
        "id": "evt_1",
        "type": "generic.event",
        "occurred_at": occurred_at.isoformat(),
        "payload": {"value": 1},
        "metadata": {"source": "test"},
    }


def test_webhook_retry_policy_retries_transient_statuses_only():
    policy = RetryPolicy(
        max_attempts=3,
        retry_status_codes=(408, 429, 500, 502, 503, 504),
        retry_exceptions=True,
        base_delay_seconds=1.0,
        max_delay_seconds=4.0,
        rng=lambda: 1.0,
    )

    assert policy.decision(attempt=1, status_code=503).should_retry
    assert not policy.decision(attempt=1, status_code=400).should_retry
    assert not policy.decision(attempt=3, status_code=503).should_retry
    assert policy.decision(attempt=2, status_code=503).next_delay_seconds == 2.0


def test_default_webhook_retry_policy_has_sensible_backoff():
    assert DEFAULT_WEBHOOK_RETRY_POLICY.max_attempts == 3
    assert (
        DEFAULT_WEBHOOK_RETRY_POLICY.base_delay_seconds,
        DEFAULT_WEBHOOK_RETRY_POLICY.max_delay_seconds,
    ) == (1.0, 30.0)


def _envelope() -> WebhookEnvelope:
    return WebhookEnvelope(
        id="evt_1",
        type="generic.event",
        occurred_at=datetime.now(UTC),
        payload={"value": 1},
    )


async def test_http_webhook_dispatcher_posts_signed_body_through_the_client():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = HttpWebhookDispatcher(signer=signer, client=client)

        result = await dispatcher.dispatch("https://example.test/webhooks", _envelope())

    assert result.status_code == 202
    assert str(seen[0].url) == "https://example.test/webhooks"
    assert "x-webhook-signature" in seen[0].headers
    assert json.loads(seen[0].content)["id"] == "evt_1"


async def test_http_webhook_dispatcher_reports_transport_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = HttpWebhookDispatcher(signer=signer, client=client)

        result = await dispatcher.dispatch("https://example.test/webhooks", _envelope())

    assert result.status_code is None
    assert result.error == "refused"


async def test_http_webhook_dispatcher_applies_timeout_policy_to_send():
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(202)

    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = HttpWebhookDispatcher(
            signer=signer,
            client=client,
            timeout_policy=TimeoutPolicy(timeout_seconds=0.01),
        )

        result = await dispatcher.dispatch("https://example.test/webhooks", _envelope())

    assert result.status_code is None
    assert result.error == "Webhook dispatch timed out"


async def test_webhook_addon_owns_the_http_client_and_closes_it_on_the_stack():
    resources = ApplicationResources()
    secret = "secret"  # pragma: allowlist secret

    stack = await open_addon(
        WebhookAddon(),
        resources,
        _settings(WEBHOOKS_ENABLED=True, WEBHOOK_SIGNING_SECRET=secret),
    )

    assert resources.webhook_dispatcher is not None
    client = resources.webhook_dispatcher._client
    assert client.is_closed is False

    await stack.aclose()

    assert client.is_closed is True


def test_webhook_addon_respects_enabled_flag():
    addon = WebhookAddon()
    secret = "secret"  # pragma: allowlist secret

    assert addon.is_enabled(_settings(WEBHOOKS_ENABLED=False)) is False
    assert addon.is_enabled(
        _settings(WEBHOOKS_ENABLED=True, WEBHOOK_SIGNING_SECRET=secret)
    )


def test_webhook_signer_accepts_recent_past_timestamp():
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    now = datetime.now(UTC)
    timestamp = int((now - timedelta(seconds=299)).timestamp())
    signature = signer.sign(b"{}", timestamp=timestamp)

    assert signer.verify(
        b"{}", signature=signature, timestamp=timestamp, now=int(now.timestamp())
    )
