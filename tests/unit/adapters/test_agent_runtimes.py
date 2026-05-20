import pytest

from app.adapters.agents.langgraph import LangGraphAgentRuntime
from app.adapters.agents.simple import SimpleAgentRuntime
from app.adapters.langchain.chat_models import TemplateFakeChatModel
from app.adapters.observability.debug import DebugObservability
from app.contracts.agents import AgentRequest
from app.core.redaction import RedactionPolicy
from app.modules.usage.tracker import InMemoryUsageTracker


async def test_simple_agent_runtime_runs_task_with_llm_and_events():
    usage_tracker = InMemoryUsageTracker()
    runtime = SimpleAgentRuntime(
        chat_model=TemplateFakeChatModel(model_name="fake-chat"),
        observability=DebugObservability(),
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
    assert response.output["content"].startswith("fake-chat response:")
    assert [event.name for event in response.events] == ["llm.request", "llm.response"]
    assert usage_tracker.records[0].operation == "agent.run"
    assert runtime.graph is not None
    assert hasattr(runtime.graph, "ainvoke")


async def test_langgraph_adapter_is_import_safe_and_requires_runtime():
    runtime = LangGraphAgentRuntime()

    with pytest.raises(RuntimeError, match="LangGraph runtime is not configured"):
        await runtime.run(AgentRequest(task="run graph"))
