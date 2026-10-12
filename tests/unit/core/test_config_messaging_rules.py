import pytest
from pydantic import ValidationError

from tests.factories import build_test_settings

_TASKS_ON = {"QUEUE_ENABLED": True, "TASKS_ENABLED": True}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"TASKS_ENABLED": True}, "TASKS_ENABLED requires QUEUE_ENABLED"),
        (
            {"QUEUE_ENABLED": True, "QUEUE_BACKEND": "redis"},
            "QUEUE_BACKEND=redis requires REDIS_ENABLED",
        ),
        (
            {**_TASKS_ON, "TASK_STORE_BACKEND": "postgres"},
            "TASK_STORE_BACKEND=postgres requires DATABASE_ENABLED",
        ),
        (
            {**_TASKS_ON, "TASK_STORE_BACKEND": "redis"},
            "TASK_STORE_BACKEND=redis requires REDIS_ENABLED",
        ),
        (
            {**_TASKS_ON, "TASKS_DISPATCH_BACKEND": "outbox"},
            "TASKS_DISPATCH_BACKEND=outbox requires OUTBOX_ENABLED",
        ),
        (
            {
                **_TASKS_ON,
                "DATABASE_ENABLED": True,
                "OUTBOX_ENABLED": True,
                "TASKS_DISPATCH_BACKEND": "outbox",
                "TASK_STORE_BACKEND": "memory",
            },
            "TASKS_DISPATCH_BACKEND=outbox requires TASK_STORE_BACKEND=postgres",
        ),
        (
            {"OUTBOX_ENABLED": True},
            "OUTBOX_BACKEND=postgres requires DATABASE_ENABLED",
        ),
        (
            {"WEBHOOKS_ENABLED": True},
            "WEBHOOK_SIGNING_SECRET is required when WEBHOOKS_ENABLED",
        ),
    ],
)
def test_settings_reject_inconsistent_messaging_config(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        build_test_settings(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"TASKS_ENABLED": False, "TASK_STORE_BACKEND": "postgres"},
        {"QUEUE_ENABLED": False, "QUEUE_BACKEND": "redis"},
        {"OUTBOX_ENABLED": False},
        {"WEBHOOKS_ENABLED": False},
        {**_TASKS_ON},
        {
            **_TASKS_ON,
            "DATABASE_ENABLED": True,
            "OUTBOX_ENABLED": True,
            "TASKS_DISPATCH_BACKEND": "outbox",
            "TASK_STORE_BACKEND": "postgres",
        },
    ],
)
def test_rules_apply_only_when_feature_is_enabled(
    overrides: dict[str, object],
) -> None:
    build_test_settings(**overrides)
