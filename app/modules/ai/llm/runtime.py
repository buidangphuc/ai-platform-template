from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import Settings
from app.modules.ai.llm.langfuse import (
    LangfuseLLMTracker,
    LLMTraceContext,
    build_langfuse_tracker,
)
from app.modules.ai.llm.router import ModelRouter


@dataclass(frozen=True)
class LLMInstance:
    chat_model: BaseChatModel
    tracker: LangfuseLLMTracker

    def trace_config(self, context: LLMTraceContext | None = None) -> dict[str, object]:
        return self.tracker.trace_config(context)


def build_chat_model(settings: Settings) -> BaseChatModel:
    return ModelRouter(settings).chat_model()


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
