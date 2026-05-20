import time
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from app.adapters.langgraph.default_graph import (
    DefaultAgentGraphState,
    build_agent_prompt,
    build_default_agent_graph,
)
from app.contracts.agents import AgentEvent, AgentRequest, AgentResponse
from app.contracts.observability import ObservabilityClient
from app.core.redaction import RedactionPolicy
from app.modules.usage.schemas import UsageRecord
from app.modules.usage.tracker import InMemoryUsageTracker


class SimpleAgentRuntime:
    def __init__(
        self,
        *,
        chat_model: BaseChatModel,
        observability: ObservabilityClient,
        redaction_policy: RedactionPolicy,
        usage_tracker: InMemoryUsageTracker | None = None,
        graph: Any | None = None,
    ) -> None:
        self.chat_model = chat_model
        self.graph = graph or build_default_agent_graph(chat_model)
        self.observability = observability
        self.redaction_policy = redaction_policy
        self.usage_tracker = usage_tracker

    async def run(self, request: AgentRequest) -> AgentResponse:
        run_id = str(uuid4())
        graph_input: DefaultAgentGraphState = {
            "task": request.task,
            "input": request.input,
            "messages": [],
        }
        prompt = build_agent_prompt(graph_input)
        events = [
            AgentEvent(
                name="llm.request",
                payload={"content": self.redaction_policy.redact_text(prompt)},
            )
        ]
        async with self.observability.start_span(
            "agent.run",
            attributes={"ai.operation": "agent.run", "app.job_id": run_id},
        ) as span:
            started_at = time.perf_counter()
            graph_result = await self.graph.ainvoke(graph_input)
            output = self._graph_output(graph_result)
            usage = self._graph_usage(graph_result)
            model = str(output.get("model") or graph_result.get("model") or "runtime")
            content = str(output.get("content", ""))
            span.set_attribute("ai.model", model)
            span.set_attribute("ai.tokens.input", usage["input_tokens"])
            span.set_attribute("ai.tokens.output", usage["output_tokens"])
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
