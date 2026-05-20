from typing import Any
from uuid import uuid4

from app.contracts.agents import AgentRequest, AgentResponse


class LangGraphAgentRuntime:
    def __init__(self, *, graph_runner: Any | None = None) -> None:
        self.graph_runner = graph_runner

    async def run(self, request: AgentRequest) -> AgentResponse:
        if self.graph_runner is None:
            raise RuntimeError("LangGraph runtime is not configured")

        if hasattr(self.graph_runner, "ainvoke"):
            result = await self.graph_runner.ainvoke(request.model_dump(mode="json"))
        elif hasattr(self.graph_runner, "invoke"):
            result = self.graph_runner.invoke(request.model_dump(mode="json"))
        else:
            raise RuntimeError("LangGraph runtime does not expose invoke or ainvoke")

        if isinstance(result, AgentResponse):
            return result
        return AgentResponse(
            run_id=(
                str(result.get("run_id", uuid4()))
                if isinstance(result, dict)
                else str(uuid4())
            ),
            status="completed",
            output=result if isinstance(result, dict) else {"result": result},
        )
