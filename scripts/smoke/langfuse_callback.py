"""Local smoke that drives a fake LLM call through the Langfuse callback.

Run against the local self-hosted Langfuse stack (`make docker-run-langfuse`)
to verify the per-instance tracker wires the LangChain callback, propagates
session/user/request metadata, and flushes on shutdown. Uses the in-process
`FakeListChatModel` so no real provider credentials are needed.
"""

import argparse
import asyncio
import json
import sys
from uuid import uuid4

from langchain_core.messages import HumanMessage

from app.core.config import get_settings
from app.modules.llm.langfuse import LLMTraceContext
from app.modules.llm.runtime import build_llm_instance


async def run_smoke(
    *,
    prompt: str,
    run_name: str,
    session_id: str,
    user_id: str,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.LANGFUSE_ENABLED:
        raise RuntimeError(
            "LANGFUSE_ENABLED is false; set it to true in .env before running "
            "the Langfuse smoke."
        )
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env "
            "before running the Langfuse smoke."
        )

    instance = build_llm_instance(
        settings,
        instance_id="langfuse-smoke",
        service_name="research-smoke",
        tags=("smoke",),
    )

    trace_config = instance.trace_config(
        LLMTraceContext(
            run_name=run_name,
            session_id=session_id,
            user_id=user_id,
            request_id=str(uuid4()),
            tags=("langfuse-smoke",),
            metadata={"smoke_run": True},
        )
    )

    response = await instance.chat_model.ainvoke(
        [HumanMessage(content=prompt)],
        trace_config,
    )
    instance.tracker.flush()

    return {
        "langfuse_base_url": settings.LANGFUSE_BASE_URL,
        "run_name": run_name,
        "session_id": session_id,
        "user_id": user_id,
        "prompt": prompt,
        "response": getattr(response, "content", str(response)),
        "tags": trace_config.get("tags", []),
        "metadata": trace_config.get("metadata", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default="Langfuse smoke ping.",
        help="Prompt sent to the fake chat model.",
    )
    parser.add_argument(
        "--run-name",
        default=f"langfuse-smoke-{uuid4().hex[:8]}",
        help="Trace run_name; surfaced as the Langfuse trace name.",
    )
    parser.add_argument(
        "--session-id",
        default=f"smoke-session-{uuid4().hex[:8]}",
        help="Langfuse session id; filterable in the Sessions view.",
    )
    parser.add_argument(
        "--user-id",
        default="local-dev",
        help="Langfuse user id; filterable in the Users view.",
    )
    args = parser.parse_args()

    try:
        result = asyncio.run(
            run_smoke(
                prompt=args.prompt,
                run_name=args.run_name,
                session_id=args.session_id,
                user_id=args.user_id,
            )
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(result, indent=2, sort_keys=True))
    print(
        f"\nOpen {result['langfuse_base_url']} and filter by "
        f"session_id={result['session_id']!r} or user_id={result['user_id']!r} "
        "to find the trace.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
