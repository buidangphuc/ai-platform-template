import json
import time
from uuid import uuid4

from app.contracts.agents import AgentEvent, AgentRequest, AgentResponse
from app.contracts.llm import ChatMessage, LLMClient, LLMRequest
from app.contracts.observability import ObservabilityClient
from app.core.redaction import RedactionPolicy
from app.modules.usage.schemas import UsageRecord
from app.modules.usage.tracker import InMemoryUsageTracker


class SimpleAgentRuntime:
    def __init__(
        self,
        *,
        llm: LLMClient,
        observability: ObservabilityClient,
        redaction_policy: RedactionPolicy,
        usage_tracker: InMemoryUsageTracker | None = None,
    ) -> None:
        self.llm = llm
        self.observability = observability
        self.redaction_policy = redaction_policy
        self.usage_tracker = usage_tracker

    async def run(self, request: AgentRequest) -> AgentResponse:
        run_id = str(uuid4())
        prompt = self._build_prompt(request)
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
            response = await self.llm.complete(
                LLMRequest(
                    messages=[ChatMessage(role="user", content=prompt)],
                    metadata={"agent_run_id": run_id},
                )
            )
            span.set_attribute("ai.model", response.model)
            span.set_attribute("ai.tokens.input", response.usage.input_tokens)
            span.set_attribute("ai.tokens.output", response.usage.output_tokens)
            if self.usage_tracker is not None:
                await self.usage_tracker.record(
                    UsageRecord(
                        operation="agent.run",
                        provider="runtime",
                        model=response.model,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
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
                    "content": self.redaction_policy.redact_text(response.content),
                    "model": response.model,
                },
            )
        )
        return AgentResponse(
            run_id=run_id,
            status="completed",
            output={
                "content": response.content,
                "model": response.model,
            },
            events=events,
        )

    def _build_prompt(self, request: AgentRequest) -> str:
        return (
            f"Task: {request.task}\n"
            f"Input: {json.dumps(request.input, sort_keys=True)}"
        )
