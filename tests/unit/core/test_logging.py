import logging

from loguru import logger

from app.core.logging import InterceptHandler, configure_logging
from app.core.request_context import reset_request_id, set_request_id


def test_configure_logging_installs_intercept_handler_once():
    configure_logging()
    configure_logging()

    intercept_handlers = [
        handler
        for handler in logging.root.handlers
        if isinstance(handler, InterceptHandler)
    ]
    assert len(intercept_handlers) == 1


def test_configure_logging_silences_noisy_loggers():
    configure_logging(noisy_loggers=("sqlalchemy.engine", "httpx"))

    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING


def test_loguru_record_contains_request_id():
    captured: list[str] = []

    configure_logging()
    sink_id = logger.add(
        lambda msg: captured.append(str(msg)),
        format="{extra[request_id]}|{message}",
    )

    token = set_request_id("req-loguru")
    try:
        logger.info("hello")
    finally:
        reset_request_id(token)
        logger.remove(sink_id)

    assert any("req-loguru|hello" in entry for entry in captured)


def test_stdlib_logger_routes_through_loguru():
    captured: list[str] = []

    configure_logging()
    sink_id = logger.add(
        lambda msg: captured.append(str(msg)),
        format="{message}",
    )

    try:
        logging.getLogger("legacy.module").error("stdlib message")
    finally:
        logger.remove(sink_id)

    assert any("stdlib message" in entry for entry in captured)
