import pytest
from pydantic import ValidationError

from tests.factories import build_test_settings


def test_defaults_leave_the_consumer_off():
    settings = build_test_settings()
    assert settings.KAFKA_CONSUMER_ENABLED is False
    assert settings.KAFKA_BOOTSTRAP_SERVERS == ""
    assert settings.KAFKA_CONSUMER_GROUP_ID == ""


@pytest.mark.parametrize(
    ("overrides", "name"),
    [
        (
            {"KAFKA_BOOTSTRAP_SERVERS": "broker:9092"},
            "KAFKA_CONSUMER_GROUP_ID",
        ),
        (
            {"KAFKA_CONSUMER_GROUP_ID": "group"},
            "KAFKA_BOOTSTRAP_SERVERS",
        ),
    ],
)
def test_enabled_consumer_requires_servers_and_group(overrides, name):
    with pytest.raises(ValidationError, match=name):
        build_test_settings(KAFKA_CONSUMER_ENABLED=True, **overrides)


def test_enabled_consumer_with_servers_and_group_is_valid():
    settings = build_test_settings(
        KAFKA_CONSUMER_ENABLED=True,
        KAFKA_BOOTSTRAP_SERVERS="broker:9092",
        KAFKA_CONSUMER_GROUP_ID="group",
    )
    assert settings.KAFKA_CONSUMER_ENABLED is True


def test_redacted_summary_hides_the_kafka_password():
    settings = build_test_settings(KAFKA_SASL_PASSWORD="hunter2-kafka")
    summary = settings.redacted_summary()
    assert summary["KAFKA_SASL_PASSWORD"] == "***"
    assert "hunter2-kafka" not in str(summary)


def test_defaults_leave_the_producer_off():
    settings = build_test_settings()
    assert settings.KAFKA_PRODUCER_ENABLED is False


def test_enabled_producer_requires_servers():
    with pytest.raises(ValidationError, match="KAFKA_BOOTSTRAP_SERVERS"):
        build_test_settings(KAFKA_PRODUCER_ENABLED=True)


def test_enabled_producer_with_servers_is_valid():
    settings = build_test_settings(
        KAFKA_PRODUCER_ENABLED=True, KAFKA_BOOTSTRAP_SERVERS="broker:9092"
    )
    assert settings.KAFKA_PRODUCER_ENABLED is True
    assert settings.KAFKA_CONSUMER_ENABLED is False
