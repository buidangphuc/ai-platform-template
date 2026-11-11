from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.bootstrap import resources as resources_module
from app.bootstrap.application import create_app
from app.core.database.model import Base
from app.modules.business.conversations.models import (
    Conversation,
    ConversationMessage,
)
from tests.factories import api_client_for, api_key_entry, build_test_settings

TABLES = [Conversation.__table__, ConversationMessage.__table__]
ALICE = {"Authorization": "Bearer alice-token"}
BOB = {"Authorization": "Bearer bob-token"}


@pytest_asyncio.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=TABLES)
    monkeypatch.setattr(resources_module, "build_engine", lambda settings: engine)
    settings = build_test_settings(
        CONVERSATIONS_ENABLED=True,
        DATABASE_ENABLED=True,
        LLM_ENABLED=True,
        AUTH_API_KEYS=",".join(
            [
                api_key_entry("alice", "alice-token", "developer"),
                api_key_entry("bob", "bob-token", "developer"),
            ]
        ),
    )
    app = create_app(settings=settings)
    async with api_client_for(app) as test_client:
        yield test_client


async def _create(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/conversations", headers=headers, json={"title": "Chat"}
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_send_list_and_read_messages(client: AsyncClient) -> None:
    conversation_id = await _create(client, ALICE)

    sent = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=ALICE,
        json={"content": "hello"},
    )
    listed = await client.get("/api/v1/conversations", headers=ALICE)
    messages = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=ALICE
    )

    assert sent.status_code == 200
    body = sent.json()
    assert body["assistant_message"]["content"] == "fake response"
    assert body["user_message"]["content"] == "hello"
    assert listed.json()["pagination"] == {"limit": 50, "offset": 0, "total": 1}
    assert [item["id"] for item in listed.json()["items"]] == [conversation_id]
    assert [(m["role"], m["content"]) for m in messages.json()] == [
        ("user", "hello"),
        ("assistant", "fake response"),
    ]
    assert [m["id"] for m in messages.json()] == [
        body["user_message"]["id"],
        body["assistant_message"]["id"],
    ]


async def test_foreign_conversation_is_not_found(client: AsyncClient) -> None:
    conversation_id = await _create(client, ALICE)
    url = f"/api/v1/conversations/{conversation_id}/messages"

    read = await client.get(url, headers=BOB)
    post = await client.post(url, headers=BOB, json={"content": "hi"})
    listed = await client.get("/api/v1/conversations", headers=BOB)

    assert read.status_code == 404
    assert post.status_code == 404
    assert read.json()["error"]["code"] == "conversation_not_found"
    assert listed.json()["items"] == []


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/conversations")

    assert response.status_code == 401
