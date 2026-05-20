from typing import Literal

from pydantic import BaseModel, Field

PromptTemplateType = Literal["chat", "string"]


class PromptTemplate(BaseModel):
    name: str
    version: str
    template: str
    template_type: PromptTemplateType = "chat"
    messages: list[tuple[str, str]] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    test_cases: list[dict[str, object]] = Field(default_factory=list)


class PromptRender(BaseModel):
    name: str
    version: str
    content: str
    variables: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
