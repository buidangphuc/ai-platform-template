import time
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.redaction import RedactionPolicy
from app.modules.agents.default_graph import (
    DefaultAgentGraphState,
    build_agent_prompt,
    build_default_agent_graph,
)
from app.modules.agents.schemas import AgentEvent, AgentRequest, AgentResponse
from app.modules.rag.service import KnowledgeRetrievalService
from app.modules.rag.tools import build_knowledge_search_tool
from app.modules.usage.schemas import UsageRecord
from app.modules.usage.tracker import InMemoryUsageTracker


class SimpleAgentRuntime:
    def __init__(
        self,
        *,
        chat_model: BaseChatModel,
        redaction_policy: RedactionPolicy,
        usage_tracker: InMemoryUsageTracker | None = None,
        knowledge_service: KnowledgeRetrievalService | None = None,
        graph: Any | None = None,
    ) -> None:
        self.chat_model = chat_model
        self.graph = graph or build_default_agent_graph(chat_model)
        self.redaction_policy = redaction_policy
        self.usage_tracker = usage_tracker
        self.knowledge_search_tool = None
        if knowledge_service is not None:
            self.set_knowledge_service(knowledge_service)

    def set_knowledge_service(
        self,
        knowledge_service: KnowledgeRetrievalService,
    ) -> None:
        self.knowledge_search_tool = build_knowledge_search_tool(knowledge_service)

    async def run(self, request: AgentRequest) -> AgentResponse:
        run_id = str(uuid4())
        input_payload = dict(request.input)
        events = []
        if self.knowledge_search_tool is not None:
            tool_payload = await self.knowledge_search_tool.ainvoke(
                {
                    "query": self._knowledge_query(request),
                    "top_k": self._knowledge_top_k(request),
                }
            )
            input_payload["knowledge_context"] = tool_payload
            events.append(
                AgentEvent(
                    name="tool.knowledge_search.response",
                    payload=self.redaction_policy.redact_mapping(tool_payload),
                )
            )

        graph_input: DefaultAgentGraphState = {
            "task": request.task,
            "input": input_payload,
            "messages": [],
        }
        prompt = build_agent_prompt(graph_input)
        events.append(
            AgentEvent(
                name="llm.request",
                payload={"content": self.redaction_policy.redact_text(prompt)},
            )
        )
        started_at = time.perf_counter()
        graph_result = await self.graph.ainvoke(graph_input)
        output = self._graph_output(graph_result)
        usage = self._graph_usage(graph_result)
        model = str(output.get("model") or graph_result.get("model") or "runtime")
        content = str(output.get("content", ""))
        if self.usage_tracker is not None:
            await self.usage_tracker.record(
                UsageRecord(
                    operation="agent.run",
                    provider="runtime",
                    model=model,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    latency_ms=(time.perf_counter() - started_at) * 1000,
                    estimated_cost=0.0,
                    metadata=self.redaction_policy.redact_mapping(
                        {"task": request.task}
                    ),
                )
            )

        events.append(
            AgentEvent(
                name="llm.response",
                payload={
                    "content": self.redaction_policy.redact_text(content),
                    "model": model,
                },
            )
        )
        return AgentResponse(
            run_id=run_id,
            status="completed",
            output={
                "content": content,
                "model": model,
            },
            events=events,
        )

    def _graph_output(self, graph_result: dict[str, object]) -> dict[str, object]:
        output = graph_result.get("output")
        return output if isinstance(output, dict) else {}

    def _graph_usage(self, graph_result: dict[str, object]) -> dict[str, int]:
        raw_usage = graph_result.get("usage")
        if not isinstance(raw_usage, dict):
            return {"input_tokens": 0, "output_tokens": 0}
        return {
            "input_tokens": int(raw_usage.get("input_tokens") or 0),
            "output_tokens": int(raw_usage.get("output_tokens") or 0),
        }

    def _knowledge_query(self, request: AgentRequest) -> str:
        for key in ("query", "question"):
            value = request.input.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return request.task

    def _knowledge_top_k(self, request: AgentRequest) -> int:
        value = request.metadata.get("knowledge_top_k", 3)
        if isinstance(value, int) and value > 0:
            return value
        return 3


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
