from pathlib import Path

from langchain_core.language_models.fake_chat_models import ParrotFakeChatModel
from langchain_core.messages import HumanMessage
from llama_index.core import Document
from llama_index.core.embeddings import MockEmbedding

from app.core.redaction import RedactionPolicy
from app.modules.agents.default_graph import build_default_agent_graph
from app.modules.rag.service import KnowledgeRetrievalService, build_rag_node_parser
from app.modules.rag.tools import build_knowledge_search_tool


def test_agent_module_uses_langgraph_without_runtime_schema_wrappers():
    assert not Path("app/modules/agents/runtime.py").exists()
    assert not Path("app/modules/agents/schemas.py").exists()


async def test_default_agent_graph_invokes_native_messages_state():
    graph = build_default_agent_graph(ParrotFakeChatModel())

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Summarize status")]}
    )

    assert "Summarize status" in result["messages"][-1].content
    assert "output" not in result
    assert hasattr(graph, "ainvoke")


async def test_default_agent_graph_accepts_langchain_tools():
    knowledge = KnowledgeRetrievalService(
        embed_model=MockEmbedding(embed_dim=16),
        node_parser=build_rag_node_parser(chunk_size=64, chunk_overlap=8),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    await knowledge.index(
        [
            Document(
                id_="doc-1",
                text="Knowledge search provides advanced retrieval context.",
            )
        ]
    )
    knowledge_tool = build_knowledge_search_tool(knowledge)

    graph = build_default_agent_graph(
        ParrotFakeChatModel(),
        tools=[knowledge_tool],
    )

    graph_nodes = graph.get_graph().nodes

    assert "tools" in graph_nodes
    assert knowledge_tool.name == "knowledge_search"
