from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.contracts.embeddings import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage
from app.contracts.llm import (
    ChatMessage,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    TokenUsage,
)


class LangChainLLMClient:
    def __init__(self, *, chat_model: BaseChatModel, default_model: str) -> None:
        self.chat_model = chat_model
        self.default_model = default_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await self.chat_model.ainvoke(
            [self._to_langchain_message(message) for message in request.messages]
        )
        usage = response.usage_metadata or {}
        response_metadata = response.response_metadata or {}
        return LLMResponse(
            content=str(response.content),
            model=str(
                response_metadata.get("model_name")
                or request.model
                or self.default_model
            ),
            finish_reason=response_metadata.get("finish_reason"),
            usage=TokenUsage(
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                total_tokens=int(usage.get("total_tokens", 0) or 0),
            ),
            tool_calls=[
                LLMToolCall(
                    id=str(tool_call.get("id") or ""),
                    name=str(tool_call.get("name") or ""),
                    arguments=str(tool_call.get("args") or ""),
                )
                for tool_call in (getattr(response, "tool_calls", None) or [])
            ],
            metadata={"response_metadata": response_metadata},
        )

    def _to_langchain_message(self, message: ChatMessage):
        if message.role == "system":
            return SystemMessage(content=message.content, name=message.name)
        if message.role == "assistant":
            return AIMessage(content=message.content, name=message.name)
        if message.role == "tool":
            return ToolMessage(
                content=message.content,
                tool_call_id=message.tool_call_id or "",
                name=message.name,
            )
        return HumanMessage(content=message.content, name=message.name)


class LangChainEmbeddingClient:
    def __init__(self, *, embeddings: Embeddings, default_model: str) -> None:
        self.embeddings = embeddings
        self.default_model = default_model

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors = await self.embeddings.aembed_documents(request.texts)
        return EmbeddingResponse(
            vectors=vectors,
            model=request.model or self.default_model,
            usage=EmbeddingUsage(),
        )
