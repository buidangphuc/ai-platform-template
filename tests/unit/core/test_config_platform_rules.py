import pytest
from pydantic import ValidationError

from tests.factories import build_test_settings


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "RATE_LIMIT_ENABLED": True,
                "RATE_LIMIT_BACKEND": "redis",
                "REDIS_ENABLED": False,
            },
            "RATE_LIMIT_BACKEND=redis requires REDIS_ENABLED",
        ),
        (
            {
                "CACHE_ENABLED": True,
                "CACHE_BACKEND": "redis",
                "REDIS_ENABLED": False,
            },
            "CACHE_BACKEND=redis requires REDIS_ENABLED",
        ),
        (
            {"IDEMPOTENCY_ENABLED": True, "DATABASE_ENABLED": False},
            "IDEMPOTENCY_BACKEND=postgres requires DATABASE_ENABLED",
        ),
        (
            {
                "QUOTA_ENABLED": True,
                "QUOTA_BACKEND": "postgres",
                "DATABASE_ENABLED": False,
            },
            "QUOTA_BACKEND=postgres requires DATABASE_ENABLED",
        ),
        (
            {
                "QUOTA_ENABLED": True,
                "QUOTA_BACKEND": "mongo",
                "MONGO_ENABLED": False,
            },
            "QUOTA_BACKEND=mongo requires MONGO_ENABLED",
        ),
        (
            {"OBJECTS_ENABLED": True, "OBJECT_BACKEND": "s3"},
            "OBJECT_BACKEND=s3 requires OBJECT_S3_BUCKET",
        ),
    ],
)
def test_enabled_feature_backend_requires_its_service(
    overrides: dict[str, object], message: str
):
    with pytest.raises(ValidationError, match=message):
        build_test_settings(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "RATE_LIMIT_ENABLED": True,
            "RATE_LIMIT_BACKEND": "redis",
            "REDIS_ENABLED": True,
        },
        {"CACHE_ENABLED": True, "CACHE_BACKEND": "redis", "REDIS_ENABLED": True},
        {"IDEMPOTENCY_ENABLED": True, "DATABASE_ENABLED": True},
        {"QUOTA_ENABLED": True, "QUOTA_BACKEND": "postgres", "DATABASE_ENABLED": True},
        {"QUOTA_ENABLED": True, "QUOTA_BACKEND": "mongo", "MONGO_ENABLED": True},
        {
            "OBJECTS_ENABLED": True,
            "OBJECT_BACKEND": "s3",
            "OBJECT_S3_BUCKET": "bucket",
        },
        # Rules apply only when the feature is enabled.
        {"RATE_LIMIT_BACKEND": "redis", "REDIS_ENABLED": False},
        {"CACHE_BACKEND": "redis", "REDIS_ENABLED": False},
        {"IDEMPOTENCY_BACKEND": "postgres", "DATABASE_ENABLED": False},
        {"QUOTA_BACKEND": "mongo", "MONGO_ENABLED": False},
        {"OBJECT_BACKEND": "s3"},
        {"QUOTA_ENABLED": True, "QUOTA_BACKEND": "memory"},
    ],
)
def test_valid_backend_combinations_pass(overrides: dict[str, object]):
    build_test_settings(**overrides)
