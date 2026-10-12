"""Lifecycle addon for webhooks: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

import httpx

from app.bootstrap.resources import ApplicationResources
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
        stack: AsyncExitStack,
    ) -> None:
        signer = WebhookSigner(
            secret=settings.WEBHOOK_SIGNING_SECRET,
            tolerance_seconds=settings.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
        )
        client = httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS)
        stack.push_async_callback(client.aclose)
        dispatcher = HttpWebhookDispatcher(
            signer=signer,
            client=client,
            timeout_policy=TimeoutPolicy(
                timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS
            ),
        )
        resources.webhook_signer = signer
        resources.webhook_dispatcher = dispatcher
