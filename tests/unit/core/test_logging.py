import logging

from app.core.logging import RequestIdFilter
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
