import pytest
from langchain_core.language_models.fake_chat_models import ParrotFakeChatModel
from llama_index.core.embeddings import MockEmbedding

from app.core.redaction import RedactionPolicy
from app.modules.agents.runtime import LangGraphAgentRuntime, SimpleAgentRuntime
from app.modules.agents.schemas import AgentRequest
from app.modules.rag.schemas import RagDocument, RagIndexRequest
from app.modules.rag.service import KnowledgeRetrievalService, build_rag_node_parser
from app.modules.usage.tracker import InMemoryUsageTracker


async def test_simple_agent_runtime_runs_task_with_llm_and_events():
    usage_tracker = InMemoryUsageTracker()
    runtime = SimpleAgentRuntime(
        chat_model=ParrotFakeChatModel(),
        redaction_policy=RedactionPolicy(mode="redacted"),
        usage_tracker=usage_tracker,
    )

    response = await runtime.run(
        AgentRequest(
            task="Summarize status",
            input={"status": "Phase 3 started"},
        )
    )

    assert response.status == "completed"
    assert "Summarize status" in response.output["content"]
    assert [event.name for event in response.events] == ["llm.request", "llm.response"]
    assert usage_tracker.records[0].operation == "agent.run"
    assert runtime.graph is not None
    assert hasattr(runtime.graph, "ainvoke")


async def test_simple_agent_runtime_uses_knowledge_search_tool_when_available():
    knowledge = KnowledgeRetrievalService(
        embed_model=MockEmbedding(embed_dim=16),
        node_parser=build_rag_node_parser(chunk_size=64, chunk_overlap=8),
        usage_tracker=InMemoryUsageTracker(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    await knowledge.index(
        RagIndexRequest(
            documents=[
                RagDocument(
                    id="doc-1",
                    text="Knowledge search provides advanced retrieval context.",
                )
            ]
        )
    )
    runtime = SimpleAgentRuntime(
        chat_model=ParrotFakeChatModel(),
        redaction_policy=RedactionPolicy(mode="redacted"),
        usage_tracker=InMemoryUsageTracker(),
        knowledge_service=knowledge,
    )

    response = await runtime.run(
        AgentRequest(
            task="What provides advanced retrieval context?",
            metadata={"knowledge_top_k": 1},
        )
    )

    assert response.status == "completed"
    assert (
        "Knowledge search provides advanced retrieval context."
        in response.output["content"]
    )
    assert "tool.knowledge_search.response" in [event.name for event in response.events]
    assert runtime.knowledge_search_tool.name == "knowledge_search"


async def test_langgraph_runtime_is_import_safe_and_requires_runtime():
    runtime = LangGraphAgentRuntime()

    with pytest.raises(RuntimeError, match="LangGraph runtime is not configured"):
        await runtime.run(AgentRequest(task="run graph"))
