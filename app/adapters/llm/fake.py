from app.contracts.llm import LLMRequest, LLMResponse, TokenUsage


class FakeLLMClient:
    def __init__(self, *, model: str = "fake-chat") -> None:
        self.model = model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.model
        last_user_message = self._last_user_message(request)
        content = f"{model} response: {last_user_message}"
        input_tokens = sum(
            max(1, len(message.content.split())) for message in request.messages
        )
        output_tokens = max(1, len(content.split()))
        return LLMResponse(
            content=content,
            model=model,
            finish_reason="stop",
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    def _last_user_message(self, request: LLMRequest) -> str:
        for message in reversed(request.messages):
            if message.role == "user":
                return message.content
        return "no user message"
