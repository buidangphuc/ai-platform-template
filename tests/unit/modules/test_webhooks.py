import dataclasses
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.bootstrap.addons.webhooks import WebhookAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.messaging.webhooks import dispatcher as dispatcher_module
from app.modules.messaging.webhooks.dispatcher import (
    DEFAULT_WEBHOOK_RETRY_POLICY,
    HttpWebhookDispatcher,
)
from app.modules.messaging.webhooks.envelope import WebhookEnvelope
from app.modules.messaging.webhooks.signing import WebhookSigner
from tests.factories import build_test_settings, open_addon
from tests.http_server import Reply


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


@pytest.fixture()
async def http_client():
    async with httpx.AsyncClient() as client:
        yield client


async def test_http_webhook_dispatcher_posts_signed_body_through_the_client(
    local_http_server, http_client
):
    local_http_server.script("/webhooks", Reply(202))
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    dispatcher = HttpWebhookDispatcher(signer=signer, client=http_client)

    result = await dispatcher.dispatch(f"{local_http_server.url}/webhooks", _envelope())

    assert result.status_code == 202
    [request] = local_http_server.requests
    assert request.method == "POST"
    assert request.headers["content-type"] == "application/json"
    assert request.json()["id"] == "evt_1"
    timestamp = int(request.headers["x-webhook-timestamp"])
    assert signer.verify(
        request.body,
        signature=request.headers["x-webhook-signature"],
        timestamp=timestamp,
        now=timestamp,
    )


async def test_http_webhook_dispatcher_reports_transport_errors(
    local_http_server, http_client
):
    local_http_server.script("/webhooks", Reply(drop=True))
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    dispatcher = HttpWebhookDispatcher(signer=signer, client=http_client)

    result = await dispatcher.send_once(
        f"{local_http_server.url}/webhooks", _envelope()
    )

    assert result.status_code is None
    assert result.error


async def test_http_webhook_dispatcher_reports_a_refused_connection(
    local_http_server, http_client
):
    url = f"{local_http_server.url}/webhooks"
    await local_http_server.stop()
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    dispatcher = HttpWebhookDispatcher(signer=signer, client=http_client)

    result = await dispatcher.send_once(url, _envelope())

    assert result.status_code is None
    assert result.error


async def test_http_webhook_dispatcher_reports_non_2xx_status(
    local_http_server, http_client
):
    local_http_server.script("/webhooks", Reply(503))
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    dispatcher = HttpWebhookDispatcher(signer=signer, client=http_client)

    result = await dispatcher.send_once(
        f"{local_http_server.url}/webhooks", _envelope()
    )

    assert result.status_code == 503
    assert not result.succeeded


async def test_http_webhook_dispatcher_applies_timeout_policy_to_send(
    local_http_server, http_client
):
    local_http_server.script("/webhooks", Reply(202, delay=0.5))
    signer = WebhookSigner(secret="secret", tolerance_seconds=300)
    dispatcher = HttpWebhookDispatcher(
        signer=signer,
        client=http_client,
        timeout_policy=TimeoutPolicy(timeout_seconds=0.05),
    )

    result = await dispatcher.send_once(
        f"{local_http_server.url}/webhooks", _envelope()
    )

    assert result.status_code is None
    assert result.error == "Webhook dispatch timed out"


class _Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _retrying_dispatcher(
    client: httpx.AsyncClient,
    sleeps: _Sleeps,
    *,
    max_attempts: int = 3,
    max_delay_seconds: float = 30.0,
    timeout_seconds: float = 10.0,
) -> HttpWebhookDispatcher:
    return HttpWebhookDispatcher(
        signer=WebhookSigner(secret="secret", tolerance_seconds=300),
        client=client,
        timeout_policy=TimeoutPolicy(timeout_seconds=timeout_seconds),
        retry_policy=dataclasses.replace(
            DEFAULT_WEBHOOK_RETRY_POLICY,
            max_attempts=max_attempts,
            max_delay_seconds=max_delay_seconds,
            rng=lambda: 1.0,
        ),
        sleep=sleeps,
    )


async def test_dispatch_retries_transient_status_then_succeeds(
    local_http_server, http_client
):
    local_http_server.script("/webhooks", Reply(503), Reply(200))
    sleeps = _Sleeps()
    dispatcher = _retrying_dispatcher(http_client, sleeps)

    result = await dispatcher.dispatch(f"{local_http_server.url}/webhooks", _envelope())

    assert result.succeeded
    assert len(local_http_server.requests_to("/webhooks")) == 2
    assert sleeps.delays == [1.0]


async def test_dispatch_does_not_retry_non_retryable_status(
    local_http_server, http_client
):
    local_http_server.script("/webhooks", Reply(400))
    sleeps = _Sleeps()
    dispatcher = _retrying_dispatcher(http_client, sleeps)

    result = await dispatcher.dispatch(f"{local_http_server.url}/webhooks", _envelope())

    assert result.status_code == 400
    assert len(local_http_server.requests_to("/webhooks")) == 1
    assert sleeps.delays == []


async def test_dispatch_stops_after_max_attempts(local_http_server, http_client):
    local_http_server.script("/webhooks", Reply(503))
    sleeps = _Sleeps()
    dispatcher = _retrying_dispatcher(http_client, sleeps, max_attempts=3)

    result = await dispatcher.dispatch(f"{local_http_server.url}/webhooks", _envelope())

    assert result.status_code == 503
    assert len(local_http_server.requests_to("/webhooks")) == 3
    assert sleeps.delays == [1.0, 2.0]


async def test_dispatch_retries_refused_connection_and_timeout(
    local_http_server, http_client
):
    local_http_server.script("/slow", Reply(202, delay=0.5))
    slow = _Sleeps()
    timing_out = _retrying_dispatcher(http_client, slow, timeout_seconds=0.05)

    timed_out = await timing_out.dispatch(f"{local_http_server.url}/slow", _envelope())

    assert timed_out.status_code is None
    assert timed_out.error == "Webhook dispatch timed out"
    assert len(local_http_server.requests_to("/slow")) == 3
    assert len(slow.delays) == 2

    url = f"{local_http_server.url}/webhooks"
    await local_http_server.stop()
    refused_sleeps = _Sleeps()
    refusing = _retrying_dispatcher(http_client, refused_sleeps)

    refused = await refusing.dispatch(url, _envelope())

    assert refused.status_code is None
    assert refused.error
    assert len(refused_sleeps.delays) == 2


async def test_dispatch_honours_numeric_retry_after(local_http_server, http_client):
    local_http_server.script(
        "/hinted", Reply(429, headers={"Retry-After": "2"}), Reply(200)
    )
    local_http_server.script(
        "/capped", Reply(429, headers={"Retry-After": "999"}), Reply(200)
    )
    hinted = _Sleeps()
    capped = _Sleeps()
    policy_cap = 30.0

    await _retrying_dispatcher(http_client, hinted).dispatch(
        f"{local_http_server.url}/hinted", _envelope()
    )
    await _retrying_dispatcher(
        http_client, capped, max_delay_seconds=policy_cap
    ).dispatch(f"{local_http_server.url}/capped", _envelope())

    assert hinted.delays == [2.0]
    assert capped.delays == [policy_cap]


async def test_each_attempt_is_signed_with_its_own_timestamp(
    local_http_server, http_client, monkeypatch
):
    clock = iter([1_700_000_000, 1_700_000_005])
    monkeypatch.setattr(
        dispatcher_module, "time", SimpleNamespace(time=lambda: next(clock))
    )
    local_http_server.script("/webhooks", Reply(503), Reply(200))
    dispatcher = _retrying_dispatcher(http_client, _Sleeps())

    await dispatcher.dispatch(f"{local_http_server.url}/webhooks", _envelope())

    first, second = local_http_server.requests_to("/webhooks")
    assert first.headers["x-webhook-timestamp"] == "1700000000"
    assert second.headers["x-webhook-timestamp"] == "1700000005"
    for request in (first, second):
        timestamp = int(request.headers["x-webhook-timestamp"])
        assert dispatcher.signer.verify(
            request.body,
            signature=request.headers["x-webhook-signature"],
            timestamp=timestamp,
            now=timestamp,
        )


async def test_send_once_makes_one_request(local_http_server, http_client):
    local_http_server.script("/webhooks", Reply(503))
    sleeps = _Sleeps()
    dispatcher = _retrying_dispatcher(http_client, sleeps)

    result = await dispatcher.send_once(
        f"{local_http_server.url}/webhooks", _envelope()
    )

    assert result.status_code == 503
    assert len(local_http_server.requests_to("/webhooks")) == 1
    assert sleeps.delays == []


async def test_webhook_addon_uses_max_attempts_setting():
    resources = ApplicationResources()
    secret = "secret"  # pragma: allowlist secret

    stack = await open_addon(
        WebhookAddon(),
        resources,
        _settings(
            WEBHOOKS_ENABLED=True, WEBHOOK_SIGNING_SECRET=secret, WEBHOOK_MAX_ATTEMPTS=5
        ),
    )

    assert resources.webhook_dispatcher is not None
    assert resources.webhook_dispatcher.retry_policy.max_attempts == 5
    await stack.aclose()


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
