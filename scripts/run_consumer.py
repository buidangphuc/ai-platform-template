from __future__ import annotations

import asyncio
import sys

from loguru import logger

from app.bootstrap import consumer as consumer_bootstrap
from app.core.config import get_settings
from app.core.logging import configure_logging


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.LOG_LEVEL, json_mode=settings.LOG_JSON)
    logger.info("settings {}", settings.redacted_summary())
    async with consumer_bootstrap.consumer_context(settings) as ctx:
        logger.info(
            "consumer_entry group_id={} topics={}",
            settings.KAFKA_CONSUMER_GROUP_ID,
            list(ctx.topics),
        )
        await ctx.run()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args:
        raise SystemExit(f"unknown arguments: {' '.join(args)}")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
