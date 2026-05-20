import time

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from app.contracts.observability import ObservabilityClient
from app.contracts.vector_store import VectorStore
from app.core.redaction import RedactionPolicy
from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.rag.chunking import TextChunker
from app.modules.rag.ingestion import RagIngestionService
from app.modules.rag.reranking import ScoreReranker
from app.modules.rag.retrievers import VectorRagRetriever
from app.modules.rag.schemas import (
    RagAnswerRequest,
    RagAnswerResponse,
    RagIndexRequest,
    RagIndexResponse,
    RagSearchRequest,
    RagSearchResponse,
)
from app.modules.usage.schemas import UsageRecord
from app.modules.usage.tracker import InMemoryUsageTracker


class RagService:
    def __init__(
        self,
        *,
        embeddings: Embeddings,
        vector_store: VectorStore,
        chat_model: BaseChatModel,
        prompt_registry: InMemoryPromptRegistry,
        chunker: TextChunker,
        usage_tracker: InMemoryUsageTracker,
        observability: ObservabilityClient,
        redaction_policy: RedactionPolicy,
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.chat_model = chat_model
        self.prompt_registry = prompt_registry
        self.chunker = chunker
        self.usage_tracker = usage_tracker
        self.observability = observability
        self.redaction_policy = redaction_policy
        self.ingestion = RagIngestionService(
            embeddings=embeddings,
            vector_store=vector_store,
            chunker=chunker,
            redaction_policy=redaction_policy,
        )
        self.retriever = VectorRagRetriever(
            embeddings=embeddings,
            vector_store=vector_store,
        )
        self.reranker = ScoreReranker()
        self.answer_chain = self._build_answer_chain("rag.answer")

    async def index(self, request: RagIndexRequest) -> RagIndexResponse:
        started_at = time.perf_counter()
        response = await self.ingestion.index(request)
        await self.usage_tracker.record(
            UsageRecord(
                operation="rag.index",
                provider="runtime",
                model="embedding",
                latency_ms=(time.perf_counter() - started_at) * 1000,
                estimated_cost=0.0,
                metadata={"chunk_count": response.chunk_count},
            )
        )
        return response

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> RagSearchResponse:
        started_at = time.perf_counter()
        response = await self.retriever.search(query, top_k=top_k, filters=filters)
        reranked_matches = self.reranker.rerank(response.matches)
        await self.usage_tracker.record(
            UsageRecord(
                operation="rag.search",
                provider="runtime",
                model="embedding",
                latency_ms=(time.perf_counter() - started_at) * 1000,
                estimated_cost=0.0,
                metadata={"top_k": top_k, "match_count": len(reranked_matches)},
            )
        )
        return RagSearchResponse(matches=reranked_matches)

    async def search_request(self, request: RagSearchRequest) -> RagSearchResponse:
        return await self.search(
            request.query,
            top_k=request.top_k,
            filters=request.filters,
        )

    async def answer(self, request: RagAnswerRequest) -> RagAnswerResponse:
        started_at = time.perf_counter()
        search_response = await self.search(
            request.question,
            top_k=request.top_k,
            filters=request.filters,
        )
        context = "\n\n".join(
            f"[{index + 1}] {match.text}"
            for index, match in enumerate(search_response.matches)
        )
        rendered_prompt = self.prompt_registry.render(
            request.prompt_name,
            version=request.prompt_version,
            variables={
                "question": request.question,
                "context": context or "No context found.",
            },
        )

        async with self.observability.start_span(
            "rag.answer",
            attributes={
                "ai.operation": "rag.answer",
                "ai.retrieval.top_k": request.top_k,
                "ai.prompt.version": rendered_prompt.version,
            },
        ) as span:
            response_message = await self._build_answer_chain(
                request.prompt_name,
                version=request.prompt_version,
            ).ainvoke(
                {
                    "question": request.question,
                    "context": context or "No context found.",
                }
            )
            usage_metadata = self._usage_metadata(response_message)
            model = self._message_model(response_message)
            span.set_attribute("ai.model", model)
            span.set_attribute("ai.tokens.input", usage_metadata["input_tokens"])
            span.set_attribute("ai.tokens.output", usage_metadata["output_tokens"])

        latency_ms = (time.perf_counter() - started_at) * 1000
        usage = await self.usage_tracker.record(
            UsageRecord(
                operation="rag.answer",
                provider="runtime",
                model=model,
                input_tokens=usage_metadata["input_tokens"],
                output_tokens=usage_metadata["output_tokens"],
                latency_ms=latency_ms,
                estimated_cost=0.0,
                metadata=self.redaction_policy.redact_mapping(
                    {
                        "prompt": rendered_prompt.content,
                        "prompt_version": rendered_prompt.version,
                    }
                ),
            )
        )
        return RagAnswerResponse(
            answer=self._message_content(response_message),
            sources=search_response.matches,
            usage=usage,
            prompt_version=rendered_prompt.version,
        )

    def _build_answer_chain(
        self,
        prompt_name: str,
        *,
        version: str | None = None,
    ) -> Runnable[dict[str, object], BaseMessage]:
        prompt = self.prompt_registry.get_langchain_prompt(prompt_name, version=version)
        return prompt | self.chat_model

    def _usage_metadata(self, message: BaseMessage) -> dict[str, int]:
        raw_usage = getattr(message, "usage_metadata", None) or {}
        input_tokens = int(
            raw_usage.get("input_tokens") or raw_usage.get("prompt_tokens") or 0
        )
        output_tokens = int(
            raw_usage.get("output_tokens") or raw_usage.get("completion_tokens") or 0
        )
        total_tokens = int(
            raw_usage.get("total_tokens") or input_tokens + output_tokens
        )
        if total_tokens and not input_tokens and not output_tokens:
            output_tokens = total_tokens
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _message_model(self, message: BaseMessage) -> str:
        metadata = getattr(message, "response_metadata", None) or {}
        model_name = metadata.get("model_name") or metadata.get("model")
        return str(model_name or getattr(self.chat_model, "model_name", "runtime"))

    def _message_content(self, message: BaseMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)
