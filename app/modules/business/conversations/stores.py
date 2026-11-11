from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database.model import utcnow
from app.modules.business.conversations.models import Conversation, ConversationMessage


class ConversationStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def create(self, principal_id: str, title: str) -> Conversation:
        row = Conversation(principal_id=principal_id, title=title)
        async with self.sessionmaker() as session, session.begin():
            session.add(row)
        return row

    async def list_for_principal(
        self, principal_id: str, *, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        owned = Conversation.principal_id == principal_id
        stmt = (
            select(Conversation)
            .where(owned)
            .order_by(Conversation.created_at.desc(), Conversation.id)
            .limit(limit)
            .offset(offset)
        )
        async with self.sessionmaker() as session:
            items = list((await session.scalars(stmt)).all())
            total = await session.scalar(
                select(func.count()).select_from(Conversation).where(owned)
            )
        return items, total or 0

    async def get_owned(
        self, conversation_id: str, principal_id: str
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.principal_id == principal_id,
        )
        async with self.sessionmaker() as session:
            return await session.scalar(stmt)

    async def messages(self, conversation_id: str) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at, ConversationMessage.id)
        )
        async with self.sessionmaker() as session:
            return list((await session.scalars(stmt)).all())

    async def append_exchange(
        self, conversation_id: str, user_content: str, assistant_content: str
    ) -> tuple[ConversationMessage, ConversationMessage]:
        now = utcnow()
        user = ConversationMessage(
            conversation_id=conversation_id,
            role="user",
            content=user_content,
            created_at=now,
        )
        assistant = ConversationMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            created_at=now + timedelta(microseconds=1),
        )
        async with self.sessionmaker() as session, session.begin():
            session.add_all([user, assistant])
        return user, assistant
