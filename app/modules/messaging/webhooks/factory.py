from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.resilience import RetryPolicy, TimeoutPolicy
from app.modules.messaging.webhooks.dispatcher import (
    DEFAULT_WEBHOOK_RETRY_POLICY,
    HttpWebhookDispatcher,
)
from app.modules.messaging.webhooks.signing import WebhookSigner


@dataclass(frozen=True)
class WebhookComponents:
    signer: WebhookSigner
    dispatcher: HttpWebhookDispatcher
    retry_policy: RetryPolicy


class WebhookAddon:
    name = "webhooks"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.WEBHOOKS_ENABLED

    def build_components(self, settings: Settings) -> WebhookComponents:
        if not settings.WEBHOOK_SIGNING_SECRET:
            raise RuntimeError(
                "WEBHOOK_SIGNING_SECRET is required when WEBHOOKS_ENABLED is true"
            )
        signer = WebhookSigner(
            secret=settings.WEBHOOK_SIGNING_SECRET,
            tolerance_seconds=settings.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
        )
        return WebhookComponents(
            signer=signer,
            dispatcher=HttpWebhookDispatcher(
                signer=signer,
                timeout_policy=TimeoutPolicy(
                    timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS
                ),
            ),
            retry_policy=DEFAULT_WEBHOOK_RETRY_POLICY,
        )

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        components = self.build_components(settings)
        resources.webhook_signer = components.signer
        resources.webhook_dispatcher = components.dispatcher
        resources.webhook_retry_policy = components.retry_policy

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        if resources.webhook_dispatcher is not None:
            await resources.webhook_dispatcher.close()
        resources.webhook_signer = None
        resources.webhook_dispatcher = None
        resources.webhook_retry_policy = None
