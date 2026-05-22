from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import attach_app_resource
from app.core.config import Settings
from app.core.resilience import TimeoutPolicy
from app.modules.webhooks.dispatcher import HttpWebhookDispatcher, WebhookRetryPolicy
from app.modules.webhooks.signing import WebhookSigner


@dataclass(frozen=True)
class WebhookComponents:
    signer: WebhookSigner
    dispatcher: HttpWebhookDispatcher
    retry_policy: WebhookRetryPolicy


class WebhookAddon:
    name = "webhooks"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.WEBHOOKS_ENABLED

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ()

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
            retry_policy=WebhookRetryPolicy(),
        )

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        components = self.build_components(settings)
        attach_app_resource(app, resources, "webhook_signer", components.signer)
        attach_app_resource(
            app,
            resources,
            "webhook_dispatcher",
            components.dispatcher,
        )
        attach_app_resource(
            app,
            resources,
            "webhook_retry_policy",
            components.retry_policy,
        )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        return None
