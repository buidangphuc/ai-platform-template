import logging

from app.core.logging import RequestIdFilter, configure_logging
from app.core.request_context import set_request_id


def test_request_id_filter_adds_request_id():
    set_request_id("req-log")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )

    RequestIdFilter().filter(record)

    assert record.request_id == "req-log"


def test_configure_logging_does_not_add_duplicate_request_id_filters():
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    root_logger.addHandler(handler)
    try:
        configure_logging()
        configure_logging()

        request_id_filters = [
            log_filter
            for log_filter in handler.filters
            if isinstance(log_filter, RequestIdFilter)
        ]
        assert len(request_id_filters) == 1
    finally:
        root_logger.removeHandler(handler)
