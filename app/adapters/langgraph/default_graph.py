import json
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph


class DefaultAgentGraphState(TypedDict, total=False):
    task: str
    input: dict[str, object]
    messages: list[BaseMessage]
    output: dict[str, object]
    usage: dict[str, int]
    model: str


def build_default_agent_graph(chat_model: BaseChatModel) -> Any:
    async def call_model(state: DefaultAgentGraphState) -> DefaultAgentGraphState:
        response = await chat_model.ainvoke(
            [HumanMessage(content=build_agent_prompt(state))]
        )
        usage = _usage_metadata(response)
        model = _message_model(chat_model, response)
        return {
            "messages": [response],
            "output": {
                "content": _message_content(response),
                "model": model,
            },
            "usage": usage,
            "model": model,
        }

    graph = StateGraph(DefaultAgentGraphState)
    graph.add_node("call_model", call_model)
    graph.add_edge(START, "call_model")
    graph.add_edge("call_model", END)
    return graph.compile()


def build_agent_prompt(state: DefaultAgentGraphState) -> str:
    return (
        f"Task: {state.get('task', '')}\n"
        f"Input: {json.dumps(state.get('input', {}), sort_keys=True)}"
    )


def _usage_metadata(message: BaseMessage) -> dict[str, int]:
    raw_usage = getattr(message, "usage_metadata", None) or {}
    input_tokens = int(
        raw_usage.get("input_tokens") or raw_usage.get("prompt_tokens") or 0
    )
    output_tokens = int(
        raw_usage.get("output_tokens") or raw_usage.get("completion_tokens") or 0
    )
    total_tokens = int(raw_usage.get("total_tokens") or input_tokens + output_tokens)
    if total_tokens and not input_tokens and not output_tokens:
        output_tokens = total_tokens
    if not total_tokens and not input_tokens and not output_tokens:
        output_tokens = _count_tokens(_message_content(message))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _message_model(chat_model: BaseChatModel, message: BaseMessage) -> str:
    metadata = getattr(message, "response_metadata", None) or {}
    model_name = metadata.get("model_name") or metadata.get("model")
    return str(model_name or getattr(chat_model, "model_name", "runtime"))


def _message_content(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def _count_tokens(content: str) -> int:
    return max(1, len(content.split())) if content else 0
