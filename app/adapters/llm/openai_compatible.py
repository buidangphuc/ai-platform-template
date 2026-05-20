from typing import Any

from openai import AsyncOpenAI

from app.contracts.llm import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    TokenUsage,
)


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.client = client or AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs: dict[str, object] = {
            "model": request.model or self.model,
            "messages": [
                self._message_to_provider(message) for message in request.messages
            ],
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.tools:
            kwargs["tools"] = request.tools

        raw_response = await self.client.chat.completions.create(**kwargs)
        choice = raw_response.choices[0]
        message = choice.message
        usage = getattr(raw_response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(
            getattr(usage, "total_tokens", input_tokens + output_tokens)
            or input_tokens + output_tokens,
        )
        return LLMResponse(
            content=str(message.content or ""),
            model=str(raw_response.model),
            finish_reason=getattr(choice, "finish_reason", None),
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            tool_calls=[
                self._tool_call_from_provider(tool_call)
                for tool_call in (getattr(message, "tool_calls", None) or [])
            ],
        )

    def _message_to_provider(self, message: ChatMessage) -> dict[str, object]:
        payload: dict[str, object] = {
            "role": message.role,
            "content": message.content,
        }
        if message.name:
            payload["name"] = message.name
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]
        return payload

    def _tool_call_from_provider(self, tool_call: Any) -> LLMToolCall:
        function = self._get_value(tool_call, "function") or {}
        return LLMToolCall(
            id=str(self._get_value(tool_call, "id") or ""),
            type=str(self._get_value(tool_call, "type") or "function"),
            name=str(self._get_value(function, "name") or ""),
            arguments=str(self._get_value(function, "arguments") or ""),
        )

    def _get_value(self, payload: Any, name: str) -> Any:
        if isinstance(payload, dict):
            return payload.get(name)
        return getattr(payload, name, None)
