from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MessageRole = Literal["user", "assistant"]


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: MessageRole
    content: str
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class SendMessageResponse(BaseModel):
    user_message: MessageView
    assistant_message: MessageView
