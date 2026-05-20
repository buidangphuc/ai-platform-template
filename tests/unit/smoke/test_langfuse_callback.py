import pytest
from langchain_core.callbacks import BaseCallbackHandler

from app.core.config import Settings
from scripts.smoke.langfuse_callback import run_smoke


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.flushed = False

    def flush(self) -> None:
        self.flushed = True


@pytest.fixture()
def smoke_settings(test_settings: Settings) -> Settings:
    return test_settings.model_copy(
        update={
            "LANGFUSE_ENABLED": True,
            "LANGFUSE_PUBLIC_KEY": "lf_pk_smoke",
            "LANGFUSE_SECRET_KEY": "lf_sk_smoke",  # pragma: allowlist secret
            "LANGFUSE_BASE_URL": "http://localhost:3000",
        }
    )


async def test_run_smoke_flushes_tracker_and_returns_observable_metadata(
    monkeypatch: pytest.MonkeyPatch,
    smoke_settings: Settings,
):
    fake_client = _FakeLangfuseClient()
    callback_invocations: list[str] = []

    monkeypatch.setattr(
        "scripts.smoke.langfuse_callback.get_settings",
        lambda: smoke_settings,
    )
    monkeypatch.setattr(
        "app.modules.llm.langfuse._build_langfuse_client",
        lambda settings: fake_client,
    )

    class _SpyHandler(BaseCallbackHandler):
        def __init__(self) -> None:
            super().__init__()
            callback_invocations.append("constructed")

        def on_chat_model_start(self, *args, **kwargs) -> None:
            callback_invocations.append("on_chat_model_start")

        def on_llm_end(self, *args, **kwargs) -> None:
            callback_invocations.append("on_llm_end")

    monkeypatch.setattr(
        "app.modules.llm.langfuse.LangfuseLLMTracker._new_callback_handler",
        lambda self: _SpyHandler(),
    )

    result = await run_smoke(
        prompt="ping",
        run_name="smoke.run",
        session_id="sess-1",
        user_id="user-1",
    )

    assert result["langfuse_base_url"] == "http://localhost:3000"
    assert result["run_name"] == "smoke.run"
    assert result["session_id"] == "sess-1"
    assert result["user_id"] == "user-1"
    assert result["response"] == "fake response"
    assert "langfuse-smoke" in result["tags"]
    assert result["metadata"]["langfuse_session_id"] == "sess-1"
    assert result["metadata"]["langfuse_user_id"] == "user-1"
    assert result["metadata"]["smoke_run"] is True
    assert callback_invocations[0] == "constructed"
    assert "on_chat_model_start" in callback_invocations
    assert "on_llm_end" in callback_invocations
    assert fake_client.flushed is True


async def test_run_smoke_fails_fast_when_langfuse_disabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    monkeypatch.setattr(
        "scripts.smoke.langfuse_callback.get_settings",
        lambda: test_settings,
    )

    with pytest.raises(RuntimeError, match="LANGFUSE_ENABLED is false"):
        await run_smoke(
            prompt="ping",
            run_name="smoke.run",
            session_id="sess-1",
            user_id="user-1",
        )


async def test_run_smoke_requires_credentials_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    settings = test_settings.model_copy(
        update={
            "LANGFUSE_ENABLED": True,
            "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
        }
    )
    monkeypatch.setattr(
        "scripts.smoke.langfuse_callback.get_settings",
        lambda: settings,
    )

    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        await run_smoke(
            prompt="ping",
            run_name="smoke.run",
            session_id="sess-1",
            user_id="user-1",
        )
