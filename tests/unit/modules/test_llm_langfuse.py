from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.modules.llm.langfuse import (
    LangfuseLLMTracker,
    LLMTraceContext,
    build_langfuse_tracker,
)
from app.modules.llm.runtime import build_llm_instance


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.prompts = []
        self.scores = []
        self.flushed = False

    def get_prompt(self, name: str, **kwargs):
        self.prompts.append((name, kwargs))
        return {"name": name, "kwargs": kwargs}

    def create_score(self, **kwargs):
        self.scores.append(kwargs)
        return {"score_id": "score-1", **kwargs}

    def flush(self) -> None:
        self.flushed = True


def test_langfuse_tracker_builds_isolated_callback_config_per_llm_instance():
    callbacks = []

    def callback_factory():
        callback = object()
        callbacks.append(callback)
        return callback

    support_tracker = LangfuseLLMTracker(
        instance_id="support-answer",
        service_name="support",
        enabled=True,
        client=FakeLangfuseClient(),
        callback_handler_factory=callback_factory,
    )
    finance_tracker = LangfuseLLMTracker(
        instance_id="finance-audit",
        service_name="finance",
        enabled=True,
        client=FakeLangfuseClient(),
        callback_handler_factory=callback_factory,
    )

    support_config = support_tracker.trace_config(
        LLMTraceContext(
            run_name="support.answer",
            session_id="session-1",
            user_id="user-1",
            request_id="request-1",
            tags=("rag",),
            metadata={"tenant": "tenant-a"},
        )
    )
    finance_config = finance_tracker.trace_config(
        LLMTraceContext(run_name="finance.audit")
    )

    assert support_config["callbacks"] == [callbacks[0]]
    assert finance_config["callbacks"] == [callbacks[1]]
    assert support_config["callbacks"][0] is not finance_config["callbacks"][0]
    assert support_config["run_name"] == "support.answer"
    assert support_config["metadata"]["llm_instance_id"] == "support-answer"
    assert support_config["metadata"]["service_name"] == "support"
    assert support_config["metadata"]["request_id"] == "request-1"
    assert support_config["metadata"]["langfuse_session_id"] == "session-1"
    assert support_config["metadata"]["langfuse_user_id"] == "user-1"
    assert support_config["metadata"]["tenant"] == "tenant-a"
    assert "llm_instance:support-answer" in support_config["tags"]
    assert "service:support" in support_config["tags"]
    assert "rag" in support_config["tags"]
    assert finance_config["metadata"]["llm_instance_id"] == "finance-audit"
    assert finance_config["metadata"]["service_name"] == "finance"


def test_disabled_langfuse_tracker_keeps_instance_metadata_without_callbacks():
    tracker = LangfuseLLMTracker(
        instance_id="local-dev",
        service_name="sandbox",
        enabled=False,
    )

    config = tracker.trace_config(LLMTraceContext(run_name="local.run"))

    assert "callbacks" not in config
    assert config["run_name"] == "local.run"
    assert config["metadata"]["llm_instance_id"] == "local-dev"
    assert config["metadata"]["service_name"] == "sandbox"


def test_langfuse_tracker_fetches_prompts_with_cache_and_label_controls():
    client = FakeLangfuseClient()
    tracker = LangfuseLLMTracker(
        instance_id="planner",
        service_name="research",
        enabled=True,
        client=client,
        prompt_cache_ttl_seconds=300,
    )

    prompt = tracker.get_prompt("agent-planner", label="staging")

    assert prompt == {
        "name": "agent-planner",
        "kwargs": {"label": "staging", "cache_ttl_seconds": 300},
    }
    assert client.prompts == [
        ("agent-planner", {"label": "staging", "cache_ttl_seconds": 300})
    ]


def test_langfuse_tracker_records_custom_eval_scores_not_feedback():
    client = FakeLangfuseClient()
    tracker = LangfuseLLMTracker(
        instance_id="judge",
        service_name="eval",
        enabled=True,
        client=client,
    )

    result = tracker.score_trace(
        trace_id="trace-1",
        name="correctness",
        value=0.83,
        data_type="NUMERIC",
        comment="passes custom eval threshold",
    )

    assert result["trace_id"] == "trace-1"
    assert client.scores == [
        {
            "trace_id": "trace-1",
            "name": "correctness",
            "value": 0.83,
            "data_type": "NUMERIC",
            "comment": "passes custom eval threshold",
        }
    ]


def test_build_langfuse_tracker_requires_credentials_when_enabled(test_settings):
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    try:
        build_langfuse_tracker(
            settings,
            instance_id="missing-credentials",
            service_name="test",
        )
    except RuntimeError as exc:
        assert "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY" in str(exc)
    else:
        raise AssertionError("expected missing Langfuse credentials to fail")


def test_build_langfuse_tracker_uses_local_env_credentials(
    monkeypatch,
    test_settings,
):
    client = FakeLangfuseClient()

    expected_public_key = "lf_pk_local_ai_platform"  # pragma: allowlist secret
    expected_secret_key = "lf_sk_local_ai_platform"  # pragma: allowlist secret

    def fake_build_langfuse_client(settings):
        assert settings.LANGFUSE_PUBLIC_KEY == expected_public_key
        assert settings.LANGFUSE_SECRET_KEY == expected_secret_key
        assert settings.LANGFUSE_BASE_URL == "http://localhost:3000"
        return client

    monkeypatch.setattr(
        "app.modules.llm.langfuse._build_langfuse_client",
        fake_build_langfuse_client,
    )
    settings = test_settings.model_copy(
        update={
            "LANGFUSE_ENABLED": True,
            "LANGFUSE_PUBLIC_KEY": "lf_pk_local_ai_platform",
            "LANGFUSE_SECRET_KEY": "lf_sk_local_ai_platform",  # pragma: allowlist secret
            "LANGFUSE_BASE_URL": "http://localhost:3000",
        }
    )

    tracker = build_langfuse_tracker(
        settings,
        instance_id="local-instance",
        service_name="local-service",
    )

    assert tracker.enabled is True
    assert tracker.client is client


def test_build_llm_instance_keeps_chat_model_native_and_tracker_separate(
    monkeypatch,
    test_settings,
):
    def fake_build_chat_model(settings):
        return FakeListChatModel(responses=["ok"])

    monkeypatch.setattr(
        "app.modules.llm.runtime.build_chat_model",
        fake_build_chat_model,
    )

    instance = build_llm_instance(
        test_settings,
        instance_id="search-rerank",
        service_name="search",
        tags=("retrieval",),
    )
    config = instance.trace_config(LLMTraceContext(run_name="search.rerank"))

    assert isinstance(instance.chat_model, FakeListChatModel)
    assert instance.tracker.instance_id == "search-rerank"
    assert instance.tracker.service_name == "search"
    assert "retrieval" in config["tags"]
