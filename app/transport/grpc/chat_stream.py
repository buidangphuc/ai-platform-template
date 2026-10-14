"""Chat streaming seam — the Chat/LLM decoupling for the gRPC ChatService.

team-ai embeds no LLM: token generation is delegated to the external LLM via the
existing router (``app.modules.ai.llm``), reached only through the ``ChatStreamer``
port. ``mock`` streams deterministic tokens offline; ``llm_router`` streams from
the router's chat model. A model-server chat backend can be added as another
adapter without touching the servicer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

from app.core.config import Settings

if TYPE_CHECKING:
    from app.modules.ai.llm.runtime import LLMInstance


class ChatStreamer(Protocol):
    def astream(self, message: str, *, session_id: str) -> AsyncIterator[str]:
        """Yield token/text deltas for the reply. Implementations are async gens."""
        ...


class MockChatStreamer:
    """Offline, deterministic — echoes the prompt word by word."""

    async def astream(self, message: str, *, session_id: str) -> AsyncIterator[str]:
        for word in f"echo: {message}".split():
            yield word + " "


class LLMRouterChatStreamer:
    """Streams from the external LLM via the existing router (no in-process model)."""

    def __init__(self, llm: LLMInstance) -> None:
        self._llm = llm

    async def astream(self, message: str, *, session_id: str) -> AsyncIterator[str]:
        from langchain_core.messages import HumanMessage

        async for chunk in self._llm.chat_model.astream(
            [HumanMessage(content=message)]
        ):
            text = _chunk_text(chunk)
            if text:
                yield text


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    # Some providers stream content as a list of parts.
    if isinstance(content, list):
        return "".join(part for part in content if isinstance(part, str))
    return ""


def build_chat_streamer(settings: Settings) -> ChatStreamer:
    if settings.CHAT_BACKEND == "mock":
        return MockChatStreamer()

    if settings.CHAT_BACKEND == "llm_router":
        from app.modules.ai.llm.runtime import build_llm_instance

        llm = build_llm_instance(
            settings,
            instance_id="grpc-chat",
            service_name="team-ai.chat",
            tags=("grpc", "chat"),
        )
        return LLMRouterChatStreamer(llm)

    raise RuntimeError(
        f"CHAT_BACKEND={settings.CHAT_BACKEND!r} not supported "
        "(use 'mock' or 'llm_router')."
    )
