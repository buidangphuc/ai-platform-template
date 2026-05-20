import time

from app.contracts.embeddings import EmbeddingClient
from app.contracts.llm import ChatMessage, LLMClient, LLMRequest
from app.contracts.observability import ObservabilityClient
from app.contracts.vector_store import VectorStore
from app.core.redaction import RedactionPolicy
from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.rag.chunking import TextChunker
from app.modules.rag.ingestion import RagIngestionService
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
        embeddings: EmbeddingClient,
        vector_store: VectorStore,
        llm: LLMClient,
        prompt_registry: InMemoryPromptRegistry,
        chunker: TextChunker,
        usage_tracker: InMemoryUsageTracker,
        observability: ObservabilityClient,
        redaction_policy: RedactionPolicy,
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.llm = llm
        self.prompt_registry = prompt_registry
        self.chunker = chunker
        self.usage_tracker = usage_tracker
        self.observability = observability
        self.redaction_policy = redaction_policy
        self.ingestion = RagIngestionService(
            embeddings=embeddings,
            vector_store=vector_store,
            chunker=chunker,
        )
        self.retriever = VectorRagRetriever(
            embeddings=embeddings,
            vector_store=vector_store,
        )

    async def index(self, request: RagIndexRequest) -> RagIndexResponse:
        return await self.ingestion.index(request)

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> RagSearchResponse:
        return await self.retriever.search(query, top_k=top_k, filters=filters)

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
            llm_response = await self.llm.complete(
                LLMRequest(
                    messages=[
                        ChatMessage(
                            role="user",
                            content=rendered_prompt.content,
                        )
                    ],
                    prompt_version=f"{rendered_prompt.name}:{rendered_prompt.version}",
                )
            )
            span.set_attribute("ai.model", llm_response.model)
            span.set_attribute("ai.tokens.input", llm_response.usage.input_tokens)
            span.set_attribute("ai.tokens.output", llm_response.usage.output_tokens)

        latency_ms = (time.perf_counter() - started_at) * 1000
        usage = await self.usage_tracker.record(
            UsageRecord(
                operation="rag.answer",
                provider="runtime",
                model=llm_response.model,
                input_tokens=llm_response.usage.input_tokens,
                output_tokens=llm_response.usage.output_tokens,
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
            answer=llm_response.content,
            sources=search_response.matches,
            usage=usage,
            prompt_version=rendered_prompt.version,
        )
