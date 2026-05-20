from dataclasses import dataclass

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.config import Settings
from app.modules.llm.langfuse import (
    LangfuseLLMTracker,
    LLMTraceContext,
    build_langfuse_tracker,
)


@dataclass(frozen=True)
class LLMInstance:
    chat_model: BaseChatModel
    tracker: LangfuseLLMTracker

    def trace_config(self, context: LLMTraceContext | None = None) -> dict[str, object]:
        return self.tracker.trace_config(context)


def build_chat_model(settings: Settings) -> BaseChatModel:
    if not settings.CHAT_PROVIDER:
        return FakeListChatModel(responses=["fake response"])
    return _init_chat_model(f"{settings.CHAT_PROVIDER}:{settings.CHAT_MODEL_NAME}")


def build_llm_instance(
    settings: Settings,
    *,
    instance_id: str,
    service_name: str,
    tags: tuple[str, ...] = (),
) -> LLMInstance:
    return LLMInstance(
        chat_model=build_chat_model(settings),
        tracker=build_langfuse_tracker(
            settings,
            instance_id=instance_id,
            service_name=service_name,
            tags=tags,
        ),
    )


def _init_chat_model(target: str) -> BaseChatModel:
    return init_chat_model(target)
