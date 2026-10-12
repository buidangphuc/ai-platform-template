"""Lifecycle addon for webhooks; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources, opened
from app.core.config import Settings
from app.core.resilience import TimeoutPolicy
from app.modules.messaging.webhooks.dispatcher import HttpWebhookDispatcher
from app.modules.messaging.webhooks.signing import WebhookSigner


class WebhookAddon:
    name = "webhooks"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.WEBHOOKS_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        signer = WebhookSigner(
            secret=settings.WEBHOOK_SIGNING_SECRET,
            tolerance_seconds=settings.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
        )
        resources.webhook_signer = signer
        resources.webhook_dispatcher = HttpWebhookDispatcher(
            signer=signer,
            timeout_policy=TimeoutPolicy(
                timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS
            ),
        )

    async def close(self, resources: ApplicationResources) -> None:
        await opened(resources.webhook_dispatcher, "webhook dispatcher").close()
