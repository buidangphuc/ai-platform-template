import logging
import sys
from typing import TYPE_CHECKING

from loguru import logger

from app.core.request_context import get_request_id

if TYPE_CHECKING:
    from loguru import Record

_NOISY_LOGGERS: tuple[str, ...] = (
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "httpx",
    "httpcore",
    "uvicorn.access",
)


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _inject_request_id(record: "Record") -> None:
    record["extra"].setdefault("request_id", get_request_id())


def configure_logging(
    *,
    level: str = "INFO",
    json_mode: bool = False,
    noisy_loggers: tuple[str, ...] = _NOISY_LOGGERS,
    enqueue: bool = False,
) -> None:
    logger.remove()
    logger.configure(patcher=_inject_request_id)

    resolved_level = level.upper()
    if json_mode:
        logger.add(
            sys.stdout,
            level=resolved_level,
            serialize=True,
            enqueue=enqueue,
            backtrace=False,
            diagnose=False,
        )
    else:
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> "
            "[req={extra[request_id]}] - <level>{message}</level>"
        )
        logger.add(
            sys.stdout,
            level=resolved_level,
            format=fmt,
            enqueue=enqueue,
            backtrace=False,
            diagnose=False,
        )

    logging.root.handlers = [
        handler
        for handler in logging.root.handlers
        if not isinstance(handler, InterceptHandler)
    ]
    logging.root.addHandler(InterceptHandler())
    logging.root.setLevel(logging.NOTSET)

    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


log = logger
