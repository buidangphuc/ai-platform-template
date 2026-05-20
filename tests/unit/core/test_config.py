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
    assert settings.TRACE_CONTENT == "redacted"
    assert settings.OPENAI_BASE_URL == "https://api.openai.com/v1"
    assert settings.LLM_MODEL == "fake-chat"
    assert settings.EMBEDDING_MODEL == "fake-embedding"
    assert settings.LLM_CACHE_BACKEND == "noop"
    assert settings.LLM_CACHE_ENABLED is False
    assert settings.OBSERVABILITY_BACKEND == "debug"
    assert settings.LOCAL_STORAGE_ROOT == ".local/storage"


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
        OPENAI_API_KEY="sk-test",  # pragma: allowlist secret
    )

    summary = settings.redacted_summary()

    assert summary["REDIS_PASSWORD"] == "***"
    assert summary["API_KEY_PEPPER"] == "***"
    assert summary["API_KEY_BOOTSTRAP_TOKEN"] == "***"
    assert summary["OPENAI_API_KEY"] == "***"
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
    assert settings._redacted_value("LLM_PROVIDER", "fake") == "fake"


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
