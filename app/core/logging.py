import logging

from app.core.request_context import get_request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(level: str = "INFO") -> None:
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [req=%(request_id)s] %(name)s - %(message)s"
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
        if not any(
            isinstance(log_filter, RequestIdFilter) for log_filter in handler.filters
        ):
            handler.addFilter(RequestIdFilter())
