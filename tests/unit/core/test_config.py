from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_are_local_safe():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
    )

    assert settings.PROJECT_NAME == "AI Solution Engineering Platform"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.POSTGRES_URL.startswith("postgresql+asyncpg://")
    assert settings.CHAT_PROVIDER == ""
    assert settings.CHAT_MODEL_NAME == ""
    assert settings.LANGFUSE_ENABLED is False
    assert settings.LANGFUSE_PUBLIC_KEY == ""
    assert settings.LANGFUSE_SECRET_KEY == ""
    assert settings.LANGFUSE_BASE_URL == "https://cloud.langfuse.com"
    assert settings.LANGFUSE_PROMPT_CACHE_TTL_SECONDS == 60


def test_settings_redacts_secret_values():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="redis-secret",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="pepper-secret",  # pragma: allowlist secret
        API_KEY_BOOTSTRAP_TOKEN="bootstrap-secret",  # pragma: allowlist secret
        LANGFUSE_SECRET_KEY="langfuse-secret",  # pragma: allowlist secret
        FUTURE_SERVICE_API_KEY="sk-test",  # pragma: allowlist secret
    )

    summary = settings.redacted_summary()

    assert summary["REDIS_PASSWORD"] == "***"
    assert summary["API_KEY_PEPPER"] == "***"
    assert summary["API_KEY_BOOTSTRAP_TOKEN"] == "***"
    assert summary["LANGFUSE_SECRET_KEY"] == "***"
    assert summary["POSTGRES_URL"] == "***"
    assert summary["ENVIRONMENT"] == "test"


def test_redacted_summary_redacts_secret_like_future_fields():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
    )

    assert settings._redacted_value("FUTURE_SERVICE_TOKEN", "token-value") == "***"
    assert settings._redacted_value("FUTURE_SIGNING_SECRET", "secret-value") == "***"
    assert (
        settings._redacted_value(
            "FUTURE_DATABASE_URL",
            "postgresql+asyncpg://user:password@localhost/db",  # pragma: allowlist secret
        )
        == "***"
    )
    assert settings._redacted_value("FUTURE_PUBLIC_VALUE", "visible") == "visible"


def test_default_rate_limit_per_minute_must_be_positive():
    for rate_limit in (0, -1):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                ENVIRONMENT="test",
                POSTGRES_HOST="localhost",
                POSTGRES_USER="postgres",
                POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
                POSTGRES_DB="ai_platform",
                REDIS_HOST="localhost",
                REDIS_PORT=6379,
                REDIS_PASSWORD="",  # pragma: allowlist secret
                REDIS_DATABASE=0,
                API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
                DEFAULT_RATE_LIMIT_PER_MINUTE=rate_limit,
            )


def test_settings_keeps_model_selection_minimal():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
        CHAT_PROVIDER="openai",
        CHAT_MODEL_NAME="gpt-4.1-mini",
    )

    assert settings.CHAT_PROVIDER == "openai"
    assert settings.CHAT_MODEL_NAME == "gpt-4.1-mini"
    assert "CHAT_MODEL" not in Settings.model_fields
    assert "LLM_PROVIDER" not in Settings.model_fields
    assert "EMBEDDING_PROVIDER" not in Settings.model_fields
    assert "FAKE_EMBEDDING_DIMENSIONS" not in Settings.model_fields
    assert "EMBEDDING_MODEL" not in Settings.model_fields
    assert "AGENT_RUNTIME" not in Settings.model_fields
    assert "ADVANCED_RETRIEVAL_ENABLED" not in Settings.model_fields
    assert "RAG_CHUNK_SIZE" not in Settings.model_fields
    assert "RAG_CHUNK_OVERLAP" not in Settings.model_fields
    assert "TRACE_CONTENT" not in Settings.model_fields
    assert "STORAGE_BACKEND" not in Settings.model_fields
    assert "JOB_BACKEND" not in Settings.model_fields
    assert "LLM_CACHE_BACKEND" not in Settings.model_fields
    assert "OBSERVABILITY_BACKEND" not in Settings.model_fields
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in Settings.model_fields
    assert "EXPERIMENT_TRACKER_BACKEND" not in Settings.model_fields


def _base_settings_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": 6379,
        "REDIS_PASSWORD": "",  # pragma: allowlist secret
        "REDIS_DATABASE": 0,
        "API_KEY_PEPPER": "test-pepper",  # pragma: allowlist secret
    }
    base.update(overrides)
    return base


def test_chat_provider_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(**_base_settings_kwargs(CHAT_PROVIDER="bedrock"))


def test_chat_model_name_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Settings(
            **_base_settings_kwargs(
                CHAT_PROVIDER="openai",
                CHAT_MODEL_NAME="gpt-9000",
            )
        )


def test_chat_provider_and_model_name_must_both_be_set():
    with pytest.raises(ValidationError):
        Settings(**_base_settings_kwargs(CHAT_PROVIDER="openai"))
    with pytest.raises(ValidationError):
        Settings(**_base_settings_kwargs(CHAT_MODEL_NAME="gpt-4.1-mini"))


def test_chat_provider_and_model_name_must_match():
    with pytest.raises(ValidationError):
        Settings(
            **_base_settings_kwargs(
                CHAT_PROVIDER="anthropic",
                CHAT_MODEL_NAME="gpt-4.1-mini",
            )
        )


def test_env_example_includes_local_langfuse_stack_defaults():
    env_example = Path(".env.example").read_text(encoding="utf-8")

    public_key_line = (
        "LANGFUSE_PUBLIC_KEY=lf_pk_local_ai_platform"  # pragma: allowlist secret
    )
    secret_key_line = (
        "LANGFUSE_SECRET_KEY=lf_sk_local_ai_platform"  # pragma: allowlist secret
    )
    project_id_line = (
        "LANGFUSE_INIT_PROJECT_ID=local-ai-platform"  # pragma: allowlist secret
    )

    assert "LANGFUSE_ENABLED=true" in env_example
    assert public_key_line in env_example
    assert secret_key_line in env_example
    assert "LANGFUSE_BASE_URL=http://localhost:3000" in env_example
    assert "LANGFUSE_DOCKER_BASE_URL=http://langfuse-web:3000" in env_example
    assert project_id_line in env_example
