import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_are_local_safe():
    settings = Settings(
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
    assert settings.CHAT_MODEL == ""


def test_settings_redacts_secret_values():
    settings = Settings(
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
        FUTURE_SERVICE_API_KEY="sk-test",  # pragma: allowlist secret
    )

    summary = settings.redacted_summary()

    assert summary["REDIS_PASSWORD"] == "***"
    assert summary["API_KEY_PEPPER"] == "***"
    assert summary["API_KEY_BOOTSTRAP_TOKEN"] == "***"
    assert summary["POSTGRES_URL"] == "***"
    assert summary["ENVIRONMENT"] == "test"


def test_redacted_summary_redacts_secret_like_future_fields():
    settings = Settings(
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
        CHAT_MODEL="gpt-test",
    )

    assert settings.CHAT_MODEL == "gpt-test"
    assert "LLM_PROVIDER" not in Settings.model_fields
    assert "EMBEDDING_PROVIDER" not in Settings.model_fields
    assert "CHAT_MODEL_PROVIDER" not in Settings.model_fields
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
