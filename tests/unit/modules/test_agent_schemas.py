from app.modules.agents.schemas import AgentEvent, AgentRequest, AgentResponse


def test_agent_schemas_capture_runtime_agnostic_run_data():
    request = AgentRequest(
        task="answer with retrieval",
        input={"question": "What changed?"},
        tools=[{"name": "search", "description": "Search documents"}],
        metadata={"trace_id": "trace-1"},
    )
    event = AgentEvent(
        name="tool_call",
        payload={"tool": "search"},
    )
    response = AgentResponse(
        run_id="agent-run-1",
        status="completed",
        output={"answer": "Schema added."},
        events=[event],
    )

    assert request.task == "answer with retrieval"
    assert response.events[0].name == "tool_call"
    assert response.output["answer"] == "Schema added."
