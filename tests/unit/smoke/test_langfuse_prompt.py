import pytest

from app.core.config import Settings
from scripts.smoke.langfuse_prompt import run_smoke


class _FakePromptClient:
    def __init__(self, *, name: str, prompt: str, version: int) -> None:
        self.name = name
        self.prompt = prompt
        self.version = version

    def compile(self, **kwargs: object) -> str:
        rendered = self.prompt
        for key, value in kwargs.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.fetched: list[tuple[str, dict[str, object]]] = []
        self.flushed = False

    def create_prompt(self, **kwargs: object) -> _FakePromptClient:
        self.created.append(kwargs)
        return _FakePromptClient(
            name=str(kwargs["name"]),
            prompt=str(kwargs["prompt"]),
            version=len(self.created),
        )

    def get_prompt(self, name: str, **kwargs: object) -> _FakePromptClient:
        self.fetched.append((name, kwargs))
        latest = self.created[-1]
        return _FakePromptClient(
            name=str(latest["name"]),
            prompt=str(latest["prompt"]),
            version=len(self.created),
        )

    def flush(self) -> None:
        self.flushed = True


@pytest.fixture()
def prompt_smoke_settings(test_settings: Settings) -> Settings:
    return test_settings.model_copy(
        update={
            "LANGFUSE_ENABLED": True,
            "LANGFUSE_PUBLIC_KEY": "lf_pk_smoke",
            "LANGFUSE_SECRET_KEY": "lf_sk_smoke",  # pragma: allowlist secret
            "LANGFUSE_BASE_URL": "http://localhost:3000",
        }
    )


async def test_run_smoke_creates_then_fetches_prompt_and_compiles_variables(
    monkeypatch: pytest.MonkeyPatch,
    prompt_smoke_settings: Settings,
):
    fake_client = _FakeLangfuseClient()

    monkeypatch.setattr(
        "scripts.smoke.langfuse_prompt.get_settings",
        lambda: prompt_smoke_settings,
    )
    monkeypatch.setattr(
        "app.modules.llm.langfuse._build_langfuse_client",
        lambda settings: fake_client,
    )

    result = await run_smoke(
        prompt_name="smoke-prompt",
        label="production",
        subject="hello world",
    )

    assert fake_client.created == [
        {
            "name": "smoke-prompt",
            "prompt": (
                "You are smoke-testing the Langfuse prompt registry. "
                "Subject: {{subject}}."
            ),
            "type": "text",
            "labels": ["production"],
            "tags": ["smoke", "langfuse-prompt-smoke"],
            "commit_message": "scripts/smoke/langfuse_prompt.py",
        }
    ]
    assert fake_client.fetched == [
        ("smoke-prompt", {"label": "production", "cache_ttl_seconds": 60})
    ]
    assert fake_client.flushed is True

    assert result["prompt_name"] == "smoke-prompt"
    assert result["label"] == "production"
    assert result["created_version"] == 1
    assert result["fetched_version"] == 1
    assert result["compiled"] == (
        "You are smoke-testing the Langfuse prompt registry. Subject: hello world."
    )


async def test_run_smoke_fails_fast_when_langfuse_disabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    monkeypatch.setattr(
        "scripts.smoke.langfuse_prompt.get_settings",
        lambda: test_settings,
    )

    with pytest.raises(RuntimeError, match="LANGFUSE_ENABLED is false"):
        await run_smoke(
            prompt_name="smoke-prompt",
            label="production",
            subject="x",
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
        "scripts.smoke.langfuse_prompt.get_settings",
        lambda: settings,
    )

    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        await run_smoke(
            prompt_name="smoke-prompt",
            label="production",
            subject="x",
        )
