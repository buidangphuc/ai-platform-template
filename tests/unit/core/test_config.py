from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.factories import build_test_settings


def test_settings_defaults_are_local_safe():
    settings = build_test_settings()

    assert settings.PROJECT_NAME == "AI Solution Engineering Platform"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.POSTGRES_URL.startswith("postgresql+asyncpg://")
    assert settings.CHAT_MODEL == ""
    assert settings.LANGFUSE_ENABLED is False
    assert settings.LANGFUSE_PUBLIC_KEY == ""
    assert settings.LANGFUSE_SECRET_KEY == ""
    assert settings.LANGFUSE_BASE_URL == "https://cloud.langfuse.com"
    assert settings.LANGFUSE_PROMPT_CACHE_TTL_SECONDS == 60
    assert settings.IDEMPOTENCY_ENABLED is False
    assert settings.DATABASE_ENABLED is True
    assert settings.REDIS_ENABLED is True
    assert settings.QUEUE_ENABLED is True
    assert settings.TASKS_ENABLED is True
    assert settings.CACHE_ENABLED is False
    assert settings.CACHE_BACKEND == "memory"
    assert settings.WEBHOOKS_ENABLED is False
    assert settings.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS == 300
    assert settings.WEBHOOK_TIMEOUT_SECONDS == 10
    assert settings.SECURITY_HEADERS_ENABLED is False
    assert settings.SECURITY_HSTS_ENABLED is False
    assert settings.SECURITY_HSTS_MAX_AGE_SECONDS == 31536000
    assert settings.CHAT_FALLBACK_MODELS == ""
    assert settings.JUDGE_CHAT_MODEL == ""
    assert settings.AUTH_SUBJECT == "local-user"
    assert settings.auth_roles == ["admin"]
    assert "API_KEY_PEPPER" not in Settings.model_fields
    assert "API_KEY_BOOTSTRAP_TOKEN" not in Settings.model_fields


def test_settings_redacts_secret_values():
    settings = build_test_settings(
        REDIS_PASSWORD="redis-secret",  # pragma: allowlist secret
        AUTH_BEARER_TOKEN="bearer-secret",  # pragma: allowlist secret
        LANGFUSE_SECRET_KEY="langfuse-secret",  # pragma: allowlist secret
    )

    summary = settings.redacted_summary()

    assert summary["REDIS_PASSWORD"] == "***"
    assert summary["AUTH_BEARER_TOKEN"] == "***"
    assert summary["LANGFUSE_SECRET_KEY"] == "***"
    assert summary["POSTGRES_URL"] == "***"
    assert summary["ENVIRONMENT"] == "test"


def test_redacted_summary_redacts_secret_like_future_fields():
    settings = build_test_settings()

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


def test_principal_rate_limit_per_minute_must_be_positive():
    for rate_limit in (0, -1):
        with pytest.raises(ValidationError):
            build_test_settings(RATE_LIMIT_PRINCIPAL_PER_MINUTE=rate_limit)


def test_ip_rate_limit_per_minute_must_be_positive():
    for rate_limit in (0, -1):
        with pytest.raises(ValidationError):
            build_test_settings(RATE_LIMIT_IP_PER_MINUTE=rate_limit)


def test_settings_keeps_model_selection_minimal():
    settings = build_test_settings(
        CHAT_MODEL="openai:gpt-4.1-mini",
    )

    assert settings.CHAT_MODEL == "openai:gpt-4.1-mini"
    assert "CHAT_PROVIDER" not in Settings.model_fields
    assert "CHAT_MODEL_NAME" not in Settings.model_fields
    assert "LLM_PROVIDER" not in Settings.model_fields
    assert "EMBEDDING_PROVIDER" not in Settings.model_fields
    assert "FAKE_EMBEDDING_DIMENSIONS" not in Settings.model_fields
    assert "EMBEDDING_MODEL" not in Settings.model_fields
    assert "AGENT_RUNTIME" not in Settings.model_fields
    assert "ADVANCED_RETRIEVAL_ENABLED" not in Settings.model_fields
    assert "TRACE_CONTENT" not in Settings.model_fields
    assert "STORAGE_BACKEND" not in Settings.model_fields
    assert "JOB_BACKEND" not in Settings.model_fields
    assert "LLM_CACHE_BACKEND" not in Settings.model_fields
    assert "OBSERVABILITY_BACKEND" not in Settings.model_fields
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in Settings.model_fields
    assert "EXPERIMENT_TRACKER_BACKEND" not in Settings.model_fields


def test_chat_model_accepts_langchain_provider_model_targets_without_allowlist():
    settings = build_test_settings(CHAT_MODEL="bedrock:anthropic.claude-3-5-sonnet")

    assert settings.CHAT_MODEL == "bedrock:anthropic.claude-3-5-sonnet"


# CHAT_MODEL whitespace is no longer validated at the config layer; the LLM
# factory rejects unparseable provider targets when it tries to build the
# chat model. Drops the cosmetic strip check.


def test_worker_and_sqs_tuning_values_are_validated():
    with pytest.raises(ValidationError):
        build_test_settings(WORKER_MAX_ATTEMPTS=0)

    with pytest.raises(ValidationError):
        build_test_settings(SQS_VISIBILITY_TIMEOUT_SECONDS=-1)


def test_cache_and_webhook_settings_are_validated():
    # Backend string is intentionally not allow-listed at the config layer —
    # the corresponding factory raises on unknown values. The numeric tuning
    # values are still validated here.
    with pytest.raises(ValidationError):
        build_test_settings(CACHE_DEFAULT_TTL_SECONDS=0)

    with pytest.raises(ValidationError):
        build_test_settings(WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS=0)

    with pytest.raises(ValidationError):
        build_test_settings(WEBHOOK_TIMEOUT_SECONDS=0)


def test_auth_bearer_token_is_required_outside_dev_and_test():
    with pytest.raises(ValidationError):
        build_test_settings(ENVIRONMENT="prod", AUTH_BEARER_TOKEN="")


def test_production_rejects_openapi_docs():
    with pytest.raises(ValidationError, match="DOCS_ENABLED must be false"):
        build_test_settings(
            ENVIRONMENT="prod",
            AUTH_BEARER_TOKEN="prod-token-with-enough-entropy",
            DOCS_ENABLED=True,
            CORS_ALLOW_ORIGINS="https://app.example.com",
            TRUSTED_HOSTS="api.example.com",
        )


def test_production_rejects_wildcard_cors_and_trusted_hosts():
    for field in ("CORS_ALLOW_ORIGINS", "TRUSTED_HOSTS"):
        values = {
            "ENVIRONMENT": "prod",
            "AUTH_BEARER_TOKEN": "prod-token-with-enough-entropy",
            "DOCS_ENABLED": False,
            "CORS_ALLOW_ORIGINS": "https://app.example.com",
            "TRUSTED_HOSTS": "api.example.com",
            field: "*",
        }
        with pytest.raises(ValidationError, match=f"{field} must not contain"):
            build_test_settings(**values)


def test_production_rejects_default_or_weak_auth_tokens():
    for token in ("change-me-local-bearer-token", "short-token"):
        with pytest.raises(ValidationError, match="AUTH_BEARER_TOKEN"):
            build_test_settings(
                ENVIRONMENT="prod",
                AUTH_BEARER_TOKEN=token,  # pragma: allowlist secret
                DOCS_ENABLED=False,
                CORS_ALLOW_ORIGINS="https://app.example.com",
                TRUSTED_HOSTS="api.example.com",
            )


def test_production_accepts_locked_down_runtime_settings():
    settings = build_test_settings(
        ENVIRONMENT="production",
        AUTH_BEARER_TOKEN="prod-token-with-enough-entropy",
        DOCS_ENABLED=False,
        CORS_ALLOW_ORIGINS="https://app.example.com",
        TRUSTED_HOSTS="api.example.com",
    )

    assert settings.ENVIRONMENT == "production"


def test_auth_roles_are_parsed_from_comma_separated_string():
    settings = build_test_settings(AUTH_ROLES="admin, developer, , viewer")

    assert settings.auth_roles == ["admin", "developer", "viewer"]


def test_cors_and_trusted_hosts_are_parsed_from_comma_separated_strings():
    settings = build_test_settings(
        CORS_ALLOW_ORIGINS="https://app.example.com, http://localhost:3000",
        TRUSTED_HOSTS="api.example.com, localhost",
    )

    assert settings.cors_allow_origins == [
        "https://app.example.com",
        "http://localhost:3000",
    ]
    assert settings.trusted_hosts == ["api.example.com", "localhost"]


def test_max_request_body_bytes_must_be_positive():
    with pytest.raises(ValidationError):
        build_test_settings(MAX_REQUEST_BODY_BYTES=0)


def test_env_example_includes_app_settings_defaults():
    env_example = Path(".env.example").read_text(encoding="utf-8")

    public_key_line = (
        "LANGFUSE_PUBLIC_KEY=lf_pk_local_ai_platform"  # pragma: allowlist secret
    )
    secret_key_line = (
        "LANGFUSE_SECRET_KEY=lf_sk_local_ai_platform"  # pragma: allowlist secret
    )

    assert "LANGFUSE_ENABLED=true" in env_example
    assert public_key_line in env_example
    assert secret_key_line in env_example
    assert "LANGFUSE_BASE_URL=http://localhost:3000" in env_example
    assert "AUTH_BEARER_TOKEN=change-me-local-bearer-token" in env_example
    assert "AUTH_SUBJECT=local-user" in env_example
    assert "CHAT_MODEL=" in env_example
    assert "CORS_ALLOW_ORIGINS=*" in env_example
    assert "TRUSTED_HOSTS=*" in env_example
    assert "MAX_REQUEST_BODY_BYTES=10485760" in env_example
    assert "IDEMPOTENCY_ENABLED=false" in env_example
    assert "DATABASE_ENABLED=true" in env_example
    assert "REDIS_ENABLED=true" in env_example
    assert "QUEUE_ENABLED=true" in env_example
    assert "TASKS_ENABLED=true" in env_example
    assert "SQS_ENDPOINT_URL=" in env_example
    assert "SQS_VISIBILITY_TIMEOUT_SECONDS=0" in env_example
    assert "WORKER_MAX_ATTEMPTS=3" in env_example
    assert "CACHE_ENABLED=false" in env_example
    assert "CACHE_BACKEND=memory" in env_example
    assert "CACHE_PREFIX=app" in env_example
    assert "CACHE_DEFAULT_TTL_SECONDS=300" in env_example
    assert "WEBHOOKS_ENABLED=false" in env_example
    assert "WEBHOOK_SIGNING_SECRET=" in env_example
    assert "WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS=300" in env_example
    assert "WEBHOOK_TIMEOUT_SECONDS=10" in env_example
    assert "SECURITY_HEADERS_ENABLED=false" in env_example
    assert "SECURITY_HSTS_ENABLED=false" in env_example
    assert "SECURITY_HSTS_MAX_AGE_SECONDS=31536000" in env_example
    assert "CHAT_FALLBACK_MODELS=" in env_example
    assert "JUDGE_CHAT_MODEL=" in env_example


def test_env_langfuse_example_carries_compose_only_overrides():
    langfuse_example = Path(".env.langfuse.example").read_text(encoding="utf-8")
    project_id_line = (
        "LANGFUSE_INIT_PROJECT_ID=local-ai-platform"  # pragma: allowlist secret
    )

    assert "LANGFUSE_DOCKER_BASE_URL=http://langfuse-web:3000" in langfuse_example
    assert project_id_line in langfuse_example
    assert "LANGFUSE_NEXTAUTH_URL=http://localhost:3000" in langfuse_example
