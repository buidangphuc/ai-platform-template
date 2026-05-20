"""Local smoke that round-trips a prompt through the Langfuse registry.

Creates (or appends a new version of) a text prompt with a `production`
label, fetches it back via `LangfuseLLMTracker.get_prompt`, compiles the
`{{subject}}` variable, and prints the resolved text plus the trace
identifiers so the prompt can be inspected in the Langfuse UI.
"""

import argparse
import asyncio
import json
import sys

from app.core.config import get_settings
from app.modules.llm.langfuse import build_langfuse_tracker


async def run_smoke(
    *,
    prompt_name: str,
    label: str,
    subject: str,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.LANGFUSE_ENABLED:
        raise RuntimeError(
            "LANGFUSE_ENABLED is false; set it to true in .env before running "
            "the Langfuse prompt smoke."
        )
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env "
            "before running the Langfuse prompt smoke."
        )

    tracker = build_langfuse_tracker(
        settings,
        instance_id="langfuse-prompt-smoke",
        service_name="research-smoke",
    )

    template = (
        "You are smoke-testing the Langfuse prompt registry. " "Subject: {{subject}}."
    )
    created = tracker.client.create_prompt(
        name=prompt_name,
        prompt=template,
        type="text",
        labels=[label],
        tags=["smoke", "langfuse-prompt-smoke"],
        commit_message="scripts/smoke/langfuse_prompt.py",
    )

    fetched = tracker.get_prompt(prompt_name, label=label)
    compiled = fetched.compile(subject=subject)

    tracker.flush()

    return {
        "langfuse_base_url": settings.LANGFUSE_BASE_URL,
        "prompt_name": prompt_name,
        "label": label,
        "created_version": getattr(created, "version", None),
        "fetched_version": getattr(fetched, "version", None),
        "template": getattr(fetched, "prompt", template),
        "compiled": compiled,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt-name",
        default="langfuse-smoke-prompt",
        help="Prompt name registered in Langfuse.",
    )
    parser.add_argument(
        "--label",
        default="production",
        help="Label attached to the new prompt version and used for fetch.",
    )
    parser.add_argument(
        "--subject",
        default="local smoke",
        help="Value bound to the {{subject}} variable on compile.",
    )
    args = parser.parse_args()

    try:
        result = asyncio.run(
            run_smoke(
                prompt_name=args.prompt_name,
                label=args.label,
                subject=args.subject,
            )
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(result, indent=2, sort_keys=True))
    print(
        f"\nOpen {result['langfuse_base_url']} → Prompts → "
        f"{result['prompt_name']!r} (label={result['label']!r}, "
        f"version={result['fetched_version']}) to inspect the prompt.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
