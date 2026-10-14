"""ChatService gRPC servicer — server-streaming reply tokens.

Enforces scope, then streams deltas from the ``ChatStreamer`` seam (external LLM
via the router, or mock). A final ``done=True`` chunk closes the stream. The
Gateway adapts this to SSE for browsers at the edge (out of scope here).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import grpc

from app.transport.grpc._pb.platform.chat.v1 import chat_pb2, chat_pb2_grpc
from app.transport.grpc.chat_stream import ChatStreamer
from app.transport.grpc.context import ensure_scopes


class ChatServicer(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self, streamer: ChatStreamer) -> None:
        self._streamer = streamer

    async def StreamChat(
        self,
        request: chat_pb2.StreamChatRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[chat_pb2.StreamChatResponse]:
        await ensure_scopes(context, "chat:read")

        async for delta in self._streamer.astream(
            request.message, session_id=request.session_id
        ):
            yield chat_pb2.StreamChatResponse(delta=delta, done=False)
        yield chat_pb2.StreamChatResponse(delta="", done=True)
