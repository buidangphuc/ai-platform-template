import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.config import Settings
from app.core.config.runtime import Environment
from app.core.errors import ServiceUnavailableError
from app.core.resilience import BreakerState, CircuitBreakerPolicy
from app.modules.ai.llm.router import ModelRouter
from tests.factories import build_test_settings


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def _fallback_router(
    clock: _Clock | None = None, *, threshold: int = 2, cooldown: float = 30.0
) -> ModelRouter:
    return ModelRouter(
        _settings(CHAT_MODEL="primary", CHAT_FALLBACK_MODELS="secondary"),
        model_builder=lambda target: FakeListChatModel(responses=[target]),
        breaker_policy=CircuitBreakerPolicy(
            failure_threshold=threshold, cooldown_seconds=cooldown
        ),
        clock=clock,
    )


def test_model_router_uses_fake_model_when_default_model_is_empty():
    router = ModelRouter(_settings())

    assert isinstance(router.chat_model("default"), FakeListChatModel)


def test_model_router_uses_judge_model_when_configured():
    created: list[str] = []

    def build(target: str):
        created.append(target)
        return FakeListChatModel(responses=[target])

    router = ModelRouter(
        _settings(
            CHAT_MODEL="openai:gpt-4.1-mini",
            JUDGE_CHAT_MODEL="openai:gpt-4.1",
        ),
        model_builder=build,
    )

    model = router.chat_model("judge")

    assert isinstance(model, FakeListChatModel)
    assert created == ["openai:gpt-4.1"]


def test_model_router_builds_each_target_once():
    created: list[str] = []

    def build(target: str):
        created.append(target)
        return FakeListChatModel(responses=[target])

    router = ModelRouter(_settings(CHAT_MODEL="primary"), model_builder=build)

    assert router.model_for("primary") is router.model_for("primary")
    assert created == ["primary"]


def test_model_router_chain_is_primary_then_every_fallback_in_order():
    router = ModelRouter(
        _settings(
            CHAT_MODEL="openai:gpt-4.1-mini",
            CHAT_FALLBACK_MODELS="anthropic:claude-sonnet-4-5, openai:gpt-4.1",
        )
    )

    assert router.chain("default") == (
        "openai:gpt-4.1-mini",
        "anthropic:claude-sonnet-4-5",
        "openai:gpt-4.1",
    )


def test_model_router_chain_drops_duplicates_and_judge_has_no_fallbacks():
    router = ModelRouter(
        _settings(
            CHAT_MODEL="a",
            CHAT_FALLBACK_MODELS="b, a, b, c",
            JUDGE_CHAT_MODEL="j",
        )
    )

    assert router.chain("default") == ("a", "b", "c")
    assert router.chain("judge") == ("j",)


def test_deterministic_4xx_never_trips_failover():
    router = _fallback_router(threshold=1)

    for status in (400, 401, 413, 422):
        router.record_error("primary", error=_StatusError(status))

    assert router.select_target("default") == "primary"


def test_transient_errors_trip_failover_including_timeouts():
    router = _fallback_router(threshold=3)

    router.record_error("primary", error=_StatusError(429))
    router.record_error("primary", error=TimeoutError())
    assert router.select_target("default") == "primary"
    router.record_error("primary", error=_StatusError(503))

    assert router.select_target("default") == "secondary"


def test_primary_is_probed_after_cooldown_and_recovers_on_success():
    clock = _Clock()
    router = _fallback_router(clock, threshold=1, cooldown=30.0)
    router.record_error("primary", error=TimeoutError())
    assert router.select_target("default") == "secondary"

    clock.now += 31
    assert router.select_target("default") == "primary"  # the single probe
    assert router.select_target("default") == "secondary"  # others still fail over

    router.record_success("primary")

    assert router.select_target("default") == "primary"


def test_failed_probe_keeps_failing_over_for_another_cooldown():
    clock = _Clock()
    router = _fallback_router(clock, threshold=1, cooldown=30.0)
    router.record_error("primary", error=TimeoutError())
    clock.now += 31
    assert router.select_target("default") == "primary"

    router.record_error("primary", error=_StatusError(503))

    assert router.select_target("default") == "secondary"
    clock.now += 31
    assert router.select_target("default") == "primary"


def test_router_without_secondary_never_blocks_the_primary():
    router = ModelRouter(
        _settings(CHAT_MODEL="primary"),
        breaker_policy=CircuitBreakerPolicy(failure_threshold=1),
    )

    router.record_error("primary", error=TimeoutError())

    assert router.select_target("default") == "primary"
    assert router.try_acquire("primary") is True


def test_each_chain_target_has_its_own_breaker():
    router = _fallback_router(threshold=1)

    router.record_error("secondary", error=_StatusError(429))

    assert router.select_target("default") == "primary"
    assert router._breakers[("default", "primary")].state is BreakerState.CLOSED
    assert router._breakers[("default", "secondary")].state is BreakerState.OPEN


def _chain_router(clock: _Clock | None = None) -> ModelRouter:
    return ModelRouter(
        _settings(CHAT_MODEL="a", CHAT_FALLBACK_MODELS="b, c"),
        model_builder=lambda target: FakeListChatModel(responses=[target]),
        breaker_policy=CircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=30),
        clock=clock,
    )


def test_select_target_walks_past_every_open_breaker():
    router = _chain_router()
    router.record_error("a", error=TimeoutError())
    assert router.select_target("default") == "b"

    router.record_error("b", error=TimeoutError())
    assert router.select_target("default") == "c"


def test_select_target_raises_when_every_breaker_is_open():
    router = _chain_router()
    for target in ("a", "b", "c"):
        router.record_error(target, error=TimeoutError())

    with pytest.raises(ServiceUnavailableError):
        router.select_target("default")


def test_try_acquire_admits_the_probe_of_a_recovering_earlier_target():
    clock = _Clock()
    router = _chain_router(clock)
    router.record_error("a", error=TimeoutError())
    clock.now += 31

    assert router.try_acquire("a") is True  # the single probe
    assert router.try_acquire("a") is False


def test_model_router_resets_failure_count_on_success():
    router = _fallback_router(threshold=2)

    router.record_error("primary", error=TimeoutError())
    router.record_success("primary")
    router.record_error("primary", error=TimeoutError())

    assert router.select_target("default") == "primary"


def test_judge_falls_back_to_chat_model_with_warning_in_local_env():
    from loguru import logger

    messages: list[str] = []
    sink_id = logger.add(messages.append, level="WARNING")
    try:
        router = ModelRouter(_settings(CHAT_MODEL="primary", ENVIRONMENT="test"))
        assert router.primary_target("judge") == "primary"
        router.primary_target("judge")
    finally:
        logger.remove(sink_id)

    assert len(messages) == 1  # warned once, not per call
    assert "JUDGE_CHAT_MODEL" in messages[0]


def test_judge_equal_to_production_model_is_rejected_outside_local_env():
    router = ModelRouter(
        _settings(CHAT_MODEL="primary").model_copy(
            update={"ENVIRONMENT": Environment.PRODUCTION}
        )
    )

    with pytest.raises(ValueError, match="JUDGE_CHAT_MODEL"):
        router.primary_target("judge")


def test_judge_with_no_models_configured_does_not_raise_in_production():
    router = ModelRouter(
        _settings().model_copy(update={"ENVIRONMENT": Environment.PRODUCTION})
    )

    assert router.primary_target("judge") == ""
