from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.config import Settings
from app.core.resilience import CircuitBreaker, CircuitBreakerPolicy, RetryPolicy

ModelRole = Literal["default", "judge"]
ModelBuilder = Callable[[str], BaseChatModel]
DEFAULT_PRIMARY_4XX_THRESHOLD = 3


@dataclass
class ModelFailoverPolicy:
    primary_target: str
    secondary_target: str | None = None
    primary_4xx_threshold: int = DEFAULT_PRIMARY_4XX_THRESHOLD
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    circuit_breaker_policy: CircuitBreakerPolicy = field(init=False)
    circuit_breaker: CircuitBreaker = field(init=False)

    def __post_init__(self) -> None:
        if not self.primary_target:
            raise ValueError("primary_target is required")
        if self.primary_4xx_threshold <= 0:
            raise ValueError("primary_4xx_threshold must be positive")
        self.circuit_breaker_policy = CircuitBreakerPolicy(
            failure_threshold=self.primary_4xx_threshold,
            failure_status_range=range(400, 500),
        )
        self.circuit_breaker = self.circuit_breaker_policy.build()

    def current_target(self) -> str:
        if not self.circuit_breaker.allows_request() and self.secondary_target:
            return self.secondary_target
        return self.primary_target

    def record_success(self, model_target: str) -> None:
        if model_target == self.primary_target:
            self.circuit_breaker.record_success()

    def record_error(self, model_target: str, *, status_code: int | None) -> None:
        if model_target != self.primary_target:
            return
        self.circuit_breaker.record_failure(status_code=status_code)


class ModelRouter:
    def __init__(
        self,
        settings: Settings,
        *,
        model_builder: ModelBuilder | None = None,
    ) -> None:
        self.settings = settings
        self.model_builder = model_builder or init_chat_model

    def chat_model(self, role: ModelRole = "default") -> BaseChatModel:
        target = self.model_target(role)
        if not target:
            return FakeListChatModel(responses=["fake response"])
        return self.model_builder(target)

    def model_target(self, role: ModelRole = "default") -> str:
        if role == "judge" and self.settings.JUDGE_CHAT_MODEL:
            return self.settings.JUDGE_CHAT_MODEL
        return self.settings.CHAT_MODEL

    def fallback_models(self, role: ModelRole = "default") -> list[str]:
        primary = self.model_target(role)
        targets = [primary] if primary else []
        if role == "default":
            targets.extend(_split_csv(self.settings.CHAT_FALLBACK_MODELS)[:1])
        return targets

    def failover_policy(self, role: ModelRole = "default") -> ModelFailoverPolicy:
        targets = self.fallback_models(role)
        if not targets:
            raise ValueError("primary chat model is not configured")
        secondary = targets[1] if len(targets) > 1 else None
        return ModelFailoverPolicy(
            primary_target=targets[0], secondary_target=secondary
        )

    def trace_metadata(
        self,
        *,
        role: ModelRole,
        fallback_rank: int,
        model_target: str,
    ) -> dict[str, object]:
        return {
            "model_role": role,
            "fallback_rank": fallback_rank,
            "model_target": model_target,
        }


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
