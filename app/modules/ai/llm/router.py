from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from loguru import logger

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.resilience import CircuitBreaker, CircuitBreakerPolicy
from app.modules.ai._deps import require_langchain

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

ModelRole = Literal["default", "judge"]
ModelBuilder = Callable[[str], "BaseChatModel"]


def settings_model_builder(settings: Settings) -> ModelBuilder:
    """LangChain's provider-routing builder bound to the bounded-call settings.

    ``init_chat_model`` is imported lazily so the module stays importable
    without the ``[ai]`` extra. Every model gets an explicit output cap,
    request timeout and SDK retry budget; none of them is left to provider
    defaults.
    """

    def build(target: str) -> BaseChatModel:
        require_langchain()
        from langchain.chat_models import init_chat_model

        return init_chat_model(
            target,
            max_tokens=settings.LLM_MAX_TOKENS,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    return build


class ModelRouter:
    """Resolves the ordered LLM chain for a role and tracks each target's health.

    The ``default`` chain is ``CHAT_MODEL`` followed by every entry of
    ``CHAT_FALLBACK_MODELS`` (duplicates dropped); the ``judge`` chain is the
    judge model alone. When a chain has more than one target, each target sits
    behind its own circuit breaker that counts transient failures only (429,
    5xx, timeouts, connection errors). ``try_acquire`` is the admission gate: an
    open breaker rejects until its cooldown passes, then admits one probe. A
    single-target chain is never gated: there is nowhere to fail over to.
    Callers report each outcome with ``record_success`` / ``record_error``;
    ``LLMInstance.ainvoke`` walks the chain and does this for them.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        model_builder: ModelBuilder | None = None,
        breaker_policy: CircuitBreakerPolicy | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings
        self.model_builder = model_builder or settings_model_builder(settings)
        self.breaker_policy = breaker_policy or CircuitBreakerPolicy(
            failure_threshold=settings.LLM_BREAKER_FAILURE_THRESHOLD,
            cooldown_seconds=settings.LLM_BREAKER_COOLDOWN_SECONDS,
        )
        self._clock = clock
        self._breakers: dict[tuple[ModelRole, str], CircuitBreaker] = {}
        self._models: dict[str, BaseChatModel] = {}
        self._judge_fallback_warned = False

    def chat_model(self, role: ModelRole = "default") -> BaseChatModel:
        """Model for the next call. Does not report outcomes; prefer
        ``LLMInstance.ainvoke`` unless you need streaming/tool binding."""
        return self.model_for(self.select_target(role))

    def model_for(self, target: str) -> BaseChatModel:
        """Cached model for ``target``; the fake model when ``target`` is empty."""
        if target not in self._models:
            self._models[target] = self._build(target)
        return self._models[target]

    def primary_target(self, role: ModelRole = "default") -> str:
        if role == "judge":
            if self.settings.JUDGE_CHAT_MODEL:
                return self.settings.JUDGE_CHAT_MODEL
            if self.settings.CHAT_MODEL:
                self._on_judge_uses_production_model()
        return self.settings.CHAT_MODEL

    def chain(self, role: ModelRole = "default") -> tuple[str, ...]:
        """Targets in failover order: primary first, then each fallback."""
        targets = [self.primary_target(role)]
        if role == "default":
            targets.extend(_split_csv(self.settings.CHAT_FALLBACK_MODELS))
        return tuple(dict.fromkeys(targets))

    def try_acquire(self, target: str, role: ModelRole = "default") -> bool:
        """Admission gate for one call to ``target``. Consumes the breaker's
        probe slot when the target is being probed, so call it once per
        attempt."""
        if len(self.chain(role)) == 1:
            return True
        return self._breaker(role, target).try_acquire()

    def select_target(self, role: ModelRole = "default") -> str:
        """First target of the chain whose breaker admits a call.

        Raises ``ServiceUnavailableError`` when every breaker is open.
        """
        for target in self.chain(role):
            if self.try_acquire(target, role):
                return target
        raise ServiceUnavailableError(
            message="Every configured LLM target is unavailable",
            code="llm_unavailable",
        )

    def release(self, target: str, *, role: ModelRole = "default") -> None:
        """Return an admission taken by ``try_acquire`` without an outcome."""
        self._breaker(role, target).release_probe()

    def record_success(self, target: str, *, role: ModelRole = "default") -> None:
        self._breaker(role, target).record_success()

    def record_error(
        self,
        target: str,
        *,
        error: BaseException,
        role: ModelRole = "default",
    ) -> None:
        self._breaker(role, target).record_failure(error)

    def _build(self, target: str) -> BaseChatModel:
        if target:
            return self.model_builder(target)
        require_langchain()
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        return FakeListChatModel(responses=["fake response"])

    def _breaker(self, role: ModelRole, target: str) -> CircuitBreaker:
        key = (role, target)
        if key not in self._breakers:
            self._breakers[key] = self.breaker_policy.build(clock=self._clock)
        return self._breakers[key]

    def _on_judge_uses_production_model(self) -> None:
        message = (
            "JUDGE_CHAT_MODEL is empty, so the LLM judge would grade with the "
            "production CHAT_MODEL; set JUDGE_CHAT_MODEL to a separate model"
        )
        if not self.settings.ENVIRONMENT.is_local:
            raise ValueError(message)
        if not self._judge_fallback_warned:
            self._judge_fallback_warned = True
            logger.warning(message)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
