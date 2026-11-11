from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError
from app.modules.business.conversations.models import ConversationMessage
from app.modules.business.conversations.service import ConversationService
from app.modules.business.conversations.stores import ConversationStore


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeLlm:
    def __init__(self, reply: str = "answer", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.inputs: list[Any] = []

    async def ainvoke(self, input: Any, **kwargs: Any) -> FakeMessage:
        self.inputs.append(input)
        if self.error is not None:
            raise self.error
        return FakeMessage(self.reply)


@pytest.fixture
def store(pg_sessionmaker: async_sessionmaker[AsyncSession]) -> ConversationStore:
    return ConversationStore(pg_sessionmaker)


async def _message_count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return (
            await session.scalar(select(func.count()).select_from(ConversationMessage))
            or 0
        )


async def test_send_stores_both_messages_in_order(store: ConversationStore) -> None:
    service = ConversationService(store, FakeLlm("hi back"))  # type: ignore[arg-type]
    conversation = await service.create("alice", "Greetings")

    user, assistant = await service.send("alice", conversation.id, "hello")

    assert (user.role, user.content) == ("user", "hello")
    assert (assistant.role, assistant.content) == ("assistant", "hi back")
    stored = await service.messages("alice", conversation.id)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "hello"),
        ("assistant", "hi back"),
    ]


async def test_history_is_sent_to_the_model_in_order(store: ConversationStore) -> None:
    llm = FakeLlm("one")
    service = ConversationService(store, llm)  # type: ignore[arg-type]
    conversation = await service.create("alice", "Chat")
    await service.send("alice", conversation.id, "first")
    llm.reply = "two"

    await service.send("alice", conversation.id, "second")

    sent = llm.inputs[-1]
    assert [(type(m).__name__, m.content) for m in sent] == [
        ("HumanMessage", "first"),
        ("AIMessage", "one"),
        ("HumanMessage", "second"),
    ]
    stored = await service.messages("alice", conversation.id)
    assert [m.content for m in stored] == ["first", "one", "second", "two"]


async def test_llm_failure_stores_nothing(
    store: ConversationStore, pg_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    service = ConversationService(store, FakeLlm(error=RuntimeError("boom")))  # type: ignore[arg-type]
    conversation = await service.create("alice", "Chat")

    with pytest.raises(RuntimeError, match="boom"):
        await service.send("alice", conversation.id, "hello")

    assert await _message_count(pg_sessionmaker) == 0


async def test_store_failure_rolls_back_both_messages(
    store: ConversationStore, pg_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    conversation = await store.create("alice", "Chat")

    with pytest.raises(Exception):
        await store.append_exchange(conversation.id, "hello", None)  # type: ignore[arg-type]

    assert await _message_count(pg_sessionmaker) == 0


async def test_other_principal_gets_not_found(store: ConversationStore) -> None:
    llm = FakeLlm()
    service = ConversationService(store, llm)  # type: ignore[arg-type]
    conversation = await service.create("alice", "Private")

    with pytest.raises(NotFoundError) as sent:
        await service.send("bob", conversation.id, "hello")
    with pytest.raises(NotFoundError) as read:
        await service.messages("bob", conversation.id)

    assert sent.value.code == "conversation_not_found"
    assert sent.value.status_code == 404
    assert read.value.code == "conversation_not_found"
    assert llm.inputs == []


async def test_missing_conversation_gets_not_found(store: ConversationStore) -> None:
    service = ConversationService(store, FakeLlm())  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        await service.send("alice", "missing", "hello")


async def test_list_is_scoped_and_paginated_with_total(
    store: ConversationStore,
) -> None:
    service = ConversationService(store, FakeLlm())  # type: ignore[arg-type]
    for index in range(3):
        await service.create("alice", f"chat {index}")
    await service.create("bob", "other")

    page, total = await service.list_for_principal("alice", limit=2, offset=0)
    rest, rest_total = await service.list_for_principal("alice", limit=2, offset=2)

    assert total == rest_total == 3
    assert len(page) == 2
    assert len(rest) == 1
    assert {c.title for c in [*page, *rest]} == {"chat 0", "chat 1", "chat 2"}
    assert {c.principal_id for c in [*page, *rest]} == {"alice"}
