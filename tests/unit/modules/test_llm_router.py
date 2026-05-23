from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.config import Settings
from app.core.resilience import CircuitBreakerPolicy
from app.modules.ai.llm.router import ModelRouter
from tests.factories import build_test_settings


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


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


def test_model_router_lists_primary_then_secondary_targets():
    router = ModelRouter(
        _settings(
            CHAT_MODEL="openai:gpt-4.1-mini",
            CHAT_FALLBACK_MODELS="anthropic:claude-sonnet-4-5, openai:gpt-4.1",
        )
    )

    assert router.fallback_models("default") == [
        "openai:gpt-4.1-mini",
        "anthropic:claude-sonnet-4-5",
    ]


def test_model_router_switches_to_secondary_after_primary_4xx_threshold():
    router = ModelRouter(
        _settings(
            CHAT_MODEL="openai:gpt-4.1-mini",
            CHAT_FALLBACK_MODELS="anthropic:claude-sonnet-4-5, openai:gpt-4.1",
        )
    )

    assert router.current_target("default") == "openai:gpt-4.1-mini"
    router.record_error("openai:gpt-4.1-mini", status_code=429)
    router.record_error("openai:gpt-4.1-mini", status_code=400)
    assert router.current_target("default") == "openai:gpt-4.1-mini"

    router.record_error("openai:gpt-4.1-mini", status_code=401)

    assert router.current_target("default") == "anthropic:claude-sonnet-4-5"


def test_model_router_ignores_non_primary_and_non_4xx_errors():
    router = ModelRouter(
        _settings(
            CHAT_MODEL="primary",
            CHAT_FALLBACK_MODELS="secondary",
        ),
        breaker_policy=CircuitBreakerPolicy(
            failure_threshold=2,
            failure_status_range=range(400, 500),
        ),
    )

    router.record_error("primary", status_code=500)
    router.record_error("secondary", status_code=429)

    assert router.current_target("default") == "primary"


def test_model_router_resets_primary_4xx_count_on_success():
    router = ModelRouter(
        _settings(
            CHAT_MODEL="primary",
            CHAT_FALLBACK_MODELS="secondary",
        ),
        breaker_policy=CircuitBreakerPolicy(
            failure_threshold=2,
            failure_status_range=range(400, 500),
        ),
    )

    router.record_error("primary", status_code=429)
    router.record_success("primary")
    router.record_error("primary", status_code=429)

    assert router.current_target("default") == "primary"
