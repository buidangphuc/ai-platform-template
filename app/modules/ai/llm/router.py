from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.config import Settings
from app.core.resilience import CircuitBreaker, CircuitBreakerPolicy

ModelRole = Literal["default", "judge"]
ModelBuilder = Callable[[str], BaseChatModel]
DEFAULT_PRIMARY_4XX_THRESHOLD = 3


class ModelRouter:
    """Resolves the LLM target for a role and tracks primary-model health.

    When the primary target trips its 4xx circuit breaker, ``current_target``
    falls back to the configured secondary. Callers report outcomes via
    ``record_success`` / ``record_error`` after each invocation.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        model_builder: ModelBuilder | None = None,
        breaker_policy: CircuitBreakerPolicy | None = None,
    ) -> None:
        self.settings = settings
        self.model_builder = model_builder or init_chat_model
        self.breaker_policy = breaker_policy or CircuitBreakerPolicy(
            failure_threshold=DEFAULT_PRIMARY_4XX_THRESHOLD,
            failure_status_range=range(400, 500),
        )
        self._breakers: dict[ModelRole, CircuitBreaker] = {}

    def chat_model(self, role: ModelRole = "default") -> BaseChatModel:
        target = self.current_target(role)
        if not target:
            return FakeListChatModel(responses=["fake response"])
        return self.model_builder(target)

    def primary_target(self, role: ModelRole = "default") -> str:
        if role == "judge" and self.settings.JUDGE_CHAT_MODEL:
            return self.settings.JUDGE_CHAT_MODEL
        return self.settings.CHAT_MODEL

    def secondary_target(self, role: ModelRole = "default") -> str | None:
        if role != "default":
            return None
        fallbacks = _split_csv(self.settings.CHAT_FALLBACK_MODELS)
        return fallbacks[0] if fallbacks else None

    def fallback_models(self, role: ModelRole = "default") -> list[str]:
        primary = self.primary_target(role)
        targets = [primary] if primary else []
        secondary = self.secondary_target(role)
        if secondary:
            targets.append(secondary)
        return targets

    def current_target(self, role: ModelRole = "default") -> str:
        primary = self.primary_target(role)
        secondary = self.secondary_target(role)
        if secondary and not self._breaker(role).allows_request():
            return secondary
        return primary

    def record_success(
        self,
        target: str,
        *,
        role: ModelRole = "default",
    ) -> None:
        if target == self.primary_target(role):
            self._breaker(role).record_success()

    def record_error(
        self,
        target: str,
        *,
        status_code: int | None,
        role: ModelRole = "default",
    ) -> None:
        if target == self.primary_target(role):
            self._breaker(role).record_failure(status_code=status_code)

    def _breaker(self, role: ModelRole) -> CircuitBreaker:
        if role not in self._breakers:
            self._breakers[role] = self.breaker_policy.build()
        return self._breakers[role]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
