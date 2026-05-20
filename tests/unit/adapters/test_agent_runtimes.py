import pytest

from app.adapters.agents.langgraph import LangGraphAgentRuntime
from app.adapters.agents.simple import SimpleAgentRuntime
from app.adapters.llm.fake import FakeLLMClient
from app.adapters.observability.debug import DebugObservability
from app.contracts.agents import AgentRequest
from app.core.redaction import RedactionPolicy


async def test_simple_agent_runtime_runs_task_with_llm_and_events():
    runtime = SimpleAgentRuntime(
        llm=FakeLLMClient(model="fake-chat"),
        observability=DebugObservability(),
        redaction_policy=RedactionPolicy(mode="redacted"),
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


async def test_langgraph_adapter_is_import_safe_and_requires_runtime():
    runtime = LangGraphAgentRuntime()

    with pytest.raises(RuntimeError, match="LangGraph runtime is not configured"):
        await runtime.run(AgentRequest(task="run graph"))
