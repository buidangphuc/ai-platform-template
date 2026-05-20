import logging

from app.core.request_context import get_request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [req=%(request_id)s] %(name)s - %(message)s",
    )
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(RequestIdFilter())
