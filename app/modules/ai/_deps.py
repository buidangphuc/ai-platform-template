"""Import guards for the optional ``[ai]`` extra.

The AI stack (LangChain, Langfuse, LlamaIndex) is not installed by default —
the template core boots without it. Call these at the entry points that
genuinely need the packages so a missing install fails with an actionable
message instead of a bare ImportError. Mirrors the S3 adapter's
``_require_aioboto3`` pattern.
"""

from __future__ import annotations

import importlib

_HINT = "install the AI extra: `uv sync --extra ai` (or `pip install '.[ai]'`)"


def require_langchain() -> None:
    try:
        importlib.import_module("langchain_core")
    except ImportError as exc:  # pragma: no cover - exercised via poisoned import
        raise RuntimeError(f"LangChain is required for this feature — {_HINT}") from exc


def require_llama_index() -> None:
    try:
        importlib.import_module("llama_index.core")
    except ImportError as exc:  # pragma: no cover - exercised via poisoned import
        raise RuntimeError(
            f"LlamaIndex is required for RAG features — {_HINT}"
        ) from exc
