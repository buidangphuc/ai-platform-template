from __future__ import annotations

from pydantic import BaseModel, model_validator


class ConversationsSettingsMixin(BaseModel):
    DATABASE_ENABLED: bool
    LLM_ENABLED: bool

    CONVERSATIONS_ENABLED: bool = False

    @model_validator(mode="after")
    def validate_conversations_requirements(self) -> ConversationsSettingsMixin:
        if self.CONVERSATIONS_ENABLED:
            if not self.DATABASE_ENABLED:
                raise ValueError("CONVERSATIONS_ENABLED requires DATABASE_ENABLED")
            if not self.LLM_ENABLED:
                raise ValueError("CONVERSATIONS_ENABLED requires LLM_ENABLED")
        return self
