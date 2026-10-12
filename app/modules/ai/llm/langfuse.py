"""Per-instance Langfuse tracker: trace config, prompt registry, eval scores."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.core.config import Settings

if TYPE_CHECKING:
    from langfuse import Langfuse

LangfuseScoreDataType = Literal["NUMERIC", "CATEGORICAL", "BOOLEAN", "TEXT"]


@dataclass(frozen=True)
class LLMTraceContext:
    run_name: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class LangfuseLLMTracker:
    instance_id: str
    service_name: str
    client: Langfuse | None = None  # None = tracing disabled
    callback_handler_factory: Callable[[], Any] | None = None
    default_tags: tuple[str, ...] = ()
    prompt_cache_ttl_seconds: int = 60

    def trace_config(self, context: LLMTraceContext | None = None) -> dict[str, Any]:
        context = context or LLMTraceContext()
        config: dict[str, Any] = {
            "metadata": self._metadata(context),
            "tags": self._tags(context),
        }
        if context.run_name:
            config["run_name"] = context.run_name
        if self.client is not None:
            config["callbacks"] = [self._new_callback_handler()]
        return config

    def get_prompt(
        self,
        name: str,
        *,
        label: str | None = None,
        version: int | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> Any:
        client = self._require_client()
        kwargs: dict[str, Any] = {
            "cache_ttl_seconds": (
                self.prompt_cache_ttl_seconds
                if cache_ttl_seconds is None
                else cache_ttl_seconds
            )
        }
        if label is not None:
            kwargs["label"] = label
        if version is not None:
            kwargs["version"] = version
        return client.get_prompt(name, **kwargs)

    def score_trace(
        self,
        *,
        trace_id: str,
        name: str,
        value: float | str | bool,
        data_type: LangfuseScoreDataType,
        comment: str | None = None,
        observation_id: str | None = None,
    ) -> Any:
        client = self._require_client()
        payload: dict[str, Any] = {
            "trace_id": trace_id,
            "name": name,
            "value": value,
            "data_type": data_type,
        }
        if comment is not None:
            payload["comment"] = comment
        if observation_id is not None:
            payload["observation_id"] = observation_id
        return client.create_score(**payload)

    def flush(self) -> None:
        if self.client is not None:
            self.client.flush()

    def _metadata(self, context: LLMTraceContext) -> dict[str, object]:
        metadata = {
            "llm_instance_id": self.instance_id,
            "service_name": self.service_name,
            **context.metadata,
        }
        if context.request_id:
            metadata["request_id"] = context.request_id
        if context.session_id:
            metadata["langfuse_session_id"] = context.session_id
        if context.user_id:
            metadata["langfuse_user_id"] = context.user_id
        return metadata

    def _tags(self, context: LLMTraceContext) -> list[str]:
        return [
            f"llm_instance:{self.instance_id}",
            f"service:{self.service_name}",
            *self.default_tags,
            *context.tags,
        ]

    def _new_callback_handler(self) -> Any:
        if self.callback_handler_factory is not None:
            return self.callback_handler_factory()

        try:
            from langfuse.langchain import CallbackHandler
        except ImportError as exc:
            raise RuntimeError(
                "langfuse is required when LANGFUSE_ENABLED is true"
            ) from exc
        return CallbackHandler()

    def _require_client(self) -> Langfuse:
        if self.client is None:
            raise RuntimeError("Langfuse is disabled for this LLM instance")
        return self.client


def build_langfuse_tracker(
    settings: Settings,
    *,
    instance_id: str,
    service_name: str,
    tags: tuple[str, ...] = (),
) -> LangfuseLLMTracker:
    if not settings.LANGFUSE_ENABLED:
        return LangfuseLLMTracker(
            instance_id=instance_id,
            service_name=service_name,
            default_tags=tags,
            prompt_cache_ttl_seconds=settings.LANGFUSE_PROMPT_CACHE_TTL_SECONDS,
        )

    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required when "
            "LANGFUSE_ENABLED is true"
        )

    return LangfuseLLMTracker(
        instance_id=instance_id,
        service_name=service_name,
        client=_build_langfuse_client(settings),
        default_tags=tags,
        prompt_cache_ttl_seconds=settings.LANGFUSE_PROMPT_CACHE_TTL_SECONDS,
    )


def _build_langfuse_client(settings: Settings) -> Langfuse:
    try:
        from langfuse import Langfuse
    except ImportError as exc:
        raise RuntimeError(
            "langfuse package is required for Langfuse tracking"
        ) from exc

    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        base_url=settings.LANGFUSE_BASE_URL,
        environment=settings.ENVIRONMENT,
        release=settings.VERSION,
    )
