from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.messaging.webhooks.dispatcher import (
    DEFAULT_WEBHOOK_RETRY_POLICY,
    HttpWebhookDispatcher,
)
from app.modules.messaging.webhooks.envelope import WebhookEnvelope
from app.modules.messaging.webhooks.factory import WebhookAddon
from app.modules.messaging.webhooks.signing import WebhookSigner
from tests.factories import build_test_settings


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
        backoff_seconds=(1.0, 2.0, 4.0),
    )

    assert policy.decision(attempt=1, status_code=503).should_retry
    assert not policy.decision(attempt=1, status_code=400).should_retry
    assert not policy.decision(attempt=3, status_code=503).should_retry
    assert policy.decision(attempt=2, status_code=503).next_delay_seconds == 2.0


def test_default_webhook_retry_policy_has_sensible_backoff():
    assert DEFAULT_WEBHOOK_RETRY_POLICY.max_attempts == 3
    assert DEFAULT_WEBHOOK_RETRY_POLICY.backoff_seconds == (1.0, 5.0, 30.0)


async def test_http_webhook_dispatcher_uses_injected_post_callable():
    calls: list[dict[str, object]] = []

    async def post(url: str, *, body: bytes, headers: dict[str, str]) -> int:
        calls.append({"url": url, "body": body, "headers": headers})
        return 202

    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    dispatcher = HttpWebhookDispatcher(signer=signer, post=post)
    envelope = WebhookEnvelope(
        id="evt_1",
        type="generic.event",
        occurred_at=datetime.now(UTC),
        payload={"value": 1},
    )

    result = await dispatcher.dispatch("https://example.test/webhooks", envelope)

    assert result.status_code == 202
    assert calls[0]["url"] == "https://example.test/webhooks"
    assert "x-webhook-signature" in calls[0]["headers"]


async def test_http_webhook_dispatcher_applies_timeout_policy_to_send():
    async def slow_post(url: str, *, body: bytes, headers: dict[str, str]) -> int:
        import asyncio

        await asyncio.sleep(0.05)
        return 202

    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    dispatcher = HttpWebhookDispatcher(
        signer=signer,
        post=slow_post,
        timeout_policy=TimeoutPolicy(timeout_seconds=0.01),
    )
    envelope = WebhookEnvelope(
        id="evt_1",
        type="generic.event",
        occurred_at=datetime.now(UTC),
        payload={"value": 1},
    )

    result = await dispatcher.dispatch("https://example.test/webhooks", envelope)

    assert result.status_code is None
    assert result.error == "Webhook dispatch timed out"


def test_webhook_addon_requires_secret_when_enabled():
    addon = WebhookAddon()

    assert addon.is_enabled(_settings(WEBHOOKS_ENABLED=False)) is False
    assert addon.is_enabled(_settings(WEBHOOKS_ENABLED=True)) is True
    with pytest.raises(RuntimeError, match="WEBHOOK_SIGNING_SECRET"):
        addon.build_components(_settings(WEBHOOKS_ENABLED=True))


def test_webhook_signer_accepts_recent_past_timestamp():
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    now = datetime.now(UTC)
    timestamp = int((now - timedelta(seconds=299)).timestamp())
    signature = signer.sign(b"{}", timestamp=timestamp)

    assert signer.verify(
        b"{}", signature=signature, timestamp=timestamp, now=int(now.timestamp())
    )
