from collections.abc import Sequence
from typing import Any

from app.core.errors import NotFoundError
from app.modules.ai._deps import require_langchain
from app.modules.ai.llm.runtime import LLMInstance
from app.modules.business.conversations.models import Conversation, ConversationMessage
from app.modules.business.conversations.stores import ConversationStore


def _to_messages(history: Sequence[tuple[str, str]]) -> list[Any]:
    require_langchain()
    from langchain_core.messages import AIMessage, HumanMessage

    return [
        HumanMessage(content=content) if role == "user" else AIMessage(content=content)
        for role, content in history
    ]


class ConversationService:
    def __init__(self, store: ConversationStore, llm: LLMInstance) -> None:
        self.store = store
        self.llm = llm

    async def create(self, principal_id: str, title: str) -> Conversation:
        return await self.store.create(principal_id, title)

    async def list_for_principal(
        self, principal_id: str, *, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        return await self.store.list_for_principal(
            principal_id, limit=limit, offset=offset
        )

    async def messages(
        self, principal_id: str, conversation_id: str
    ) -> list[ConversationMessage]:
        await self._owned(principal_id, conversation_id)
        return await self.store.messages(conversation_id)

    async def send(
        self, principal_id: str, conversation_id: str, content: str
    ) -> tuple[ConversationMessage, ConversationMessage]:
        await self._owned(principal_id, conversation_id)
        history = [
            (message.role, message.content)
            for message in await self.store.messages(conversation_id)
        ]
        reply = await self.llm.ainvoke(_to_messages([*history, ("user", content)]))
        return await self.store.append_exchange(
            conversation_id, content, str(reply.text)
        )

    async def _owned(self, principal_id: str, conversation_id: str) -> Conversation:
        conversation = await self.store.get_owned(conversation_id, principal_id)
        if conversation is None:
            raise NotFoundError("Conversation not found", code="conversation_not_found")
        return conversation
