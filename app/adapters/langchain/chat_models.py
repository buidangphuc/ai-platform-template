import hashlib
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.core.config import Settings


class TemplateFakeChatModel(BaseChatModel):
    model_name: str = "fake-chat"

    @property
    def _llm_type(self) -> str:
        return "template-fake-chat"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_user_message = self._last_user_message(messages)
        content = f"{self.model_name} response: {last_user_message}"
        input_tokens = sum(
            max(1, len(str(message.content).split())) for message in messages
        )
        output_tokens = max(1, len(content.split()))
        message = AIMessage(
            content=content,
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            response_metadata={"model_name": self.model_name},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _last_user_message(self, messages: list[BaseMessage]) -> str:
        for message in reversed(messages):
            if isinstance(message, HumanMessage) or message.type == "human":
                return str(message.content)
        return "no user message"


class OpenAICompatibleChatModel(BaseChatModel):
    model_name: str
    api_key: str | None = None
    base_url: str | None = None

    @property
    def _llm_type(self) -> str:
        return "template-openai-compatible-chat"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError(
            "OpenAI-compatible LangChain chat model supports async invocation only"
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.api_key or "not-needed", base_url=self.base_url
        )
        raw_response = await client.chat.completions.create(
            model=self.model_name,
            messages=[self._message_to_provider(message) for message in messages],
            **kwargs,
        )
        choice = raw_response.choices[0]
        provider_message = choice.message
        usage = getattr(raw_response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(
            getattr(usage, "total_tokens", input_tokens + output_tokens)
            or input_tokens + output_tokens
        )
        message = AIMessage(
            content=str(provider_message.content or ""),
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            response_metadata={
                "model_name": str(raw_response.model),
                "finish_reason": getattr(choice, "finish_reason", None),
            },
            tool_calls=[
                {
                    "id": str(self._get_value(tool_call, "id") or ""),
                    "name": str(
                        self._get_value(
                            self._get_value(tool_call, "function") or {},
                            "name",
                        )
                        or ""
                    ),
                    "args": self._tool_arguments(tool_call),
                }
                for tool_call in (getattr(provider_message, "tool_calls", None) or [])
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _message_to_provider(self, message: BaseMessage) -> dict[str, object]:
        role = {
            "human": "user",
            "ai": "assistant",
            "system": "system",
            "tool": "tool",
        }.get(message.type, message.type)
        payload: dict[str, object] = {
            "role": role,
            "content": message.content,
        }
        if getattr(message, "tool_call_id", None):
            payload["tool_call_id"] = message.tool_call_id
        return payload

    def _tool_arguments(self, tool_call: Any) -> dict[str, object]:
        function = self._get_value(tool_call, "function") or {}
        raw_arguments = self._get_value(function, "arguments") or {}
        if isinstance(raw_arguments, dict):
            return raw_arguments
        return {"arguments": str(raw_arguments)}

    def _get_value(self, payload: Any, name: str) -> Any:
        if isinstance(payload, dict):
            return payload.get(name)
        return getattr(payload, name, None)


def build_chat_model(settings: Settings) -> BaseChatModel:
    if settings.LLM_PROVIDER == "fake":
        return TemplateFakeChatModel(
            model_name=settings.CHAT_MODEL or settings.LLM_MODEL
        )
    if settings.LLM_PROVIDER == "openai_compatible":
        return OpenAICompatibleChatModel(
            model_name=settings.CHAT_MODEL or settings.LLM_MODEL,
            api_key=settings.OPENAI_COMPATIBLE_API_KEY or settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_COMPATIBLE_BASE_URL or settings.OPENAI_BASE_URL,
        )
    if settings.LLM_PROVIDER == "langchain":
        if not settings.CHAT_MODEL:
            raise ValueError("CHAT_MODEL is required when LLM_PROVIDER=langchain")
        return init_chat_model(
            model=settings.CHAT_MODEL,
            model_provider=settings.CHAT_MODEL_PROVIDER or None,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")


def stable_embedding(text: str, *, dimensions: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    while len(values) < dimensions:
        for byte in digest:
            values.append((byte / 255.0) * 2 - 1)
            if len(values) == dimensions:
                break
        digest = hashlib.sha256(digest).digest()
    return values
