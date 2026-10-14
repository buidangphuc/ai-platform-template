"""Entrypoint: run team-ai as a gRPC server on the platform-core contract.

Reuses the application bootstrap (``open_application_resources`` + the default
addons) so the RAG service — with its remote model-server embedding and Qdrant
store — is wired exactly as the HTTP app wires it, then serves SearchService and
ChatService. This is the "runnable transport" the platform expects, parallel to
the HTTP app and the queue worker.

Run: ``uv run python -m scripts.run_grpc`` (needs GRPC_ENABLED=true is advisory;
this entrypoint always serves — the flag gates auto-start elsewhere).
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from loguru import logger

from app.bootstrap.addons import default_resource_addons
from app.bootstrap.resources import (
    ApplicationResources,
    close_application_resources,
    open_application_resources,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.transport.grpc.chat_stream import build_chat_streamer
from app.transport.grpc.server import serve


async def _main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.LOG_LEVEL,
        json_mode=settings.LOG_JSON,
        enqueue=settings.LOG_ENQUEUE,
    )

    app = FastAPI()
    app.state.settings = settings
    app.state.resources = ApplicationResources()
    await open_application_resources(
        app, settings, init_resources=True, addons=default_resource_addons()
    )
    logger.info("grpc.bootstrap.ready rag_enabled={}", settings.RAG_ENABLED)

    try:
        await serve(
            settings=settings,
            rag_provider=lambda: app.state.resources.rag_service,
            chat_streamer=build_chat_streamer(settings),
        )
    finally:
        await close_application_resources(app)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
