"""Thin CLI entry point for the standalone async worker."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from app.bootstrap import worker as worker_bootstrap
from app.core.config import get_settings
from app.core.logging import configure_logging


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.LOG_LEVEL, json_mode=settings.LOG_JSON)
    logger.info(
        "worker_entry queue_backend={} task_store_backend={}",
        settings.QUEUE_BACKEND,
        settings.TASK_STORE_BACKEND,
    )
    async with worker_bootstrap.worker_context(settings) as ctx:
        await ctx.worker.run()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check"]:
        try:
            worker_bootstrap.check_worker_configuration()
        except Exception as exc:
            print(f"worker configuration invalid: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return
    if args:
        raise SystemExit(f"unknown arguments: {' '.join(args)}")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
