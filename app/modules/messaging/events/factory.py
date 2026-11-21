from __future__ import annotations

import ssl
from collections.abc import Sequence
from typing import Any

from app.core.config import Settings


def _connection_options(settings: Settings) -> dict[str, Any]:
    options: dict[str, Any] = {
        "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "security_protocol": settings.KAFKA_SECURITY_PROTOCOL,
    }
    if "SASL" in settings.KAFKA_SECURITY_PROTOCOL:
        options.update(
            sasl_mechanism=settings.KAFKA_SASL_MECHANISM,
            sasl_plain_username=settings.KAFKA_SASL_USERNAME,
            sasl_plain_password=settings.KAFKA_SASL_PASSWORD,
        )
    if settings.KAFKA_SECURITY_PROTOCOL.endswith("SSL"):
        options["ssl_context"] = ssl.create_default_context(
            cafile=settings.KAFKA_SSL_CAFILE or None
        )
    return options


def build_kafka_consumer(settings: Settings, topics: Sequence[str]) -> Any:
    try:
        from aiokafka import AIOKafkaConsumer
    except ImportError as exc:
        raise RuntimeError(
            "Kafka consumer requires the [kafka] extra: "
            "uv pip install 'fastapi-template[kafka]'"
        ) from exc
    return AIOKafkaConsumer(
        *topics,
        **_connection_options(settings),
        group_id=settings.KAFKA_CONSUMER_GROUP_ID,
        enable_auto_commit=False,
        auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
        max_poll_records=settings.KAFKA_MAX_POLL_RECORDS,
    )


def build_kafka_producer(settings: Settings) -> Any:
    try:
        from aiokafka import AIOKafkaProducer
    except ImportError as exc:
        raise RuntimeError(
            "Kafka producer requires the [kafka] extra: "
            "uv pip install 'fastapi-template[kafka]'"
        ) from exc
    return AIOKafkaProducer(
        **_connection_options(settings),
        acks="all",
        enable_idempotence=True,
    )
