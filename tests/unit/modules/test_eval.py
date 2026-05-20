from typing import Any

from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import ParrotFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.adapters.observability.debug import DebugObservability
from app.adapters.vector_store.in_memory import InMemoryVectorStore
from app.core.redaction import RedactionPolicy
from app.modules.evals.rag import RAGEvaluationService
from app.modules.evals.schemas import RAGEvalCase, RAGEvalRequest
from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.rag.chunking import TextChunker
from app.modules.rag.schemas import RagDocument, RagIndexRequest
from app.modules.rag.service import RagService
from app.modules.usage.tracker import InMemoryUsageTracker


class WrongAnswerChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "wrong-answer"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="unrelated answer",
                        response_metadata={"model_name": "wrong-answer"},
                    )
                )
            ]
        )


async def test_rag_eval_service_scores_keyword_hits_against_sources():
    rag = RagService(
        embeddings=DeterministicFakeEmbedding(size=8),
        vector_store=InMemoryVectorStore(),
        chat_model=ParrotFakeChatModel(),
        prompt_registry=InMemoryPromptRegistry.with_defaults(),
        chunker=TextChunker(chunk_size=32, overlap=0),
        usage_tracker=InMemoryUsageTracker(),
        observability=DebugObservability(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    await rag.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="Phase three adds prompt registry and RAG evaluation.",
                )
            ]
        )
    )
    service = RAGEvaluationService(rag_service=rag)

    result = await service.run(
        RAGEvalRequest(
            cases=[
                RAGEvalCase(
                    id="case-1",
                    question="What does phase three add?",
                    expected_keywords=["prompt registry", "evaluation"],
                )
            ],
            top_k=1,
        )
    )

    assert result.metrics["keyword_hit_rate"] == 1.0
    assert result.items[0].passed is True


async def test_rag_eval_service_scores_generated_answer_not_only_sources():
    rag = RagService(
        embeddings=DeterministicFakeEmbedding(size=8),
        vector_store=InMemoryVectorStore(),
        chat_model=WrongAnswerChatModel(),
        prompt_registry=InMemoryPromptRegistry.with_defaults(),
        chunker=TextChunker(chunk_size=32, overlap=0),
        usage_tracker=InMemoryUsageTracker(),
        observability=DebugObservability(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    await rag.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="The source contains a hidden evaluation keyword.",
                )
            ]
        )
    )
    service = RAGEvaluationService(rag_service=rag)

    result = await service.run(
        RAGEvalRequest(
            cases=[
                RAGEvalCase(
                    id="case-1",
                    question="Return an unrelated answer.",
                    expected_keywords=["hidden evaluation keyword"],
                )
            ],
            top_k=1,
        )
    )

    assert result.metrics["keyword_hit_rate"] == 0.0
    assert result.items[0].passed is False
