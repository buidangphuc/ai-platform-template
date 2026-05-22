from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.config import Settings
from app.modules.llm.router import ModelFailoverPolicy, ModelRouter


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
    }
    base.update(overrides)
    return Settings(**base)


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


def test_model_router_parses_fallback_models():
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


def test_model_router_builds_primary_secondary_failover_policy():
    router = ModelRouter(
        _settings(
            CHAT_MODEL="openai:gpt-4.1-mini",
            CHAT_FALLBACK_MODELS="anthropic:claude-sonnet-4-5, openai:gpt-4.1",
        )
    )

    policy = router.failover_policy("default")

    assert policy.current_target() == "openai:gpt-4.1-mini"
    policy.record_error("openai:gpt-4.1-mini", status_code=429)
    policy.record_error("openai:gpt-4.1-mini", status_code=400)
    assert policy.current_target() == "openai:gpt-4.1-mini"

    policy.record_error("openai:gpt-4.1-mini", status_code=401)

    assert policy.current_target() == "anthropic:claude-sonnet-4-5"


def test_model_failover_policy_ignores_non_primary_and_non_4xx_errors():
    policy = ModelFailoverPolicy(
        primary_target="primary",
        secondary_target="secondary",
        primary_4xx_threshold=2,
    )

    policy.record_error("primary", status_code=500)
    policy.record_error("secondary", status_code=429)

    assert policy.current_target() == "primary"


def test_model_failover_policy_resets_primary_4xx_count_on_success():
    policy = ModelFailoverPolicy(
        primary_target="primary",
        secondary_target="secondary",
        primary_4xx_threshold=2,
    )

    policy.record_error("primary", status_code=429)
    policy.record_success("primary")
    policy.record_error("primary", status_code=429)

    assert policy.current_target() == "primary"


def test_model_router_builds_langfuse_metadata():
    router = ModelRouter(_settings())

    assert router.trace_metadata(
        role="judge",
        fallback_rank=1,
        model_target="openai:gpt-4.1",
    ) == {
        "model_role": "judge",
        "fallback_rank": 1,
        "model_target": "openai:gpt-4.1",
    }
