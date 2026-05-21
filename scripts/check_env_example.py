"""Fail if .env.example drifts from Settings field declarations.

Catches the common mistake of adding a new Settings field but forgetting to
document it in .env.example (or removing a field but leaving stale lines).

Computed fields (POSTGRES_URL, etc.) and underscore-prefixed pydantic internals
are skipped.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from app.core.config import Settings

ENV_EXAMPLE_PATH = Path(".env.example")
ENV_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=")


def parse_env_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def settings_field_names() -> set[str]:
    return {name for name in Settings.model_fields if not name.startswith("_")}


def main() -> int:
    if not ENV_EXAMPLE_PATH.exists():
        print(f"missing {ENV_EXAMPLE_PATH}", file=sys.stderr)
        return 1

    example_keys = parse_env_keys(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))
    field_names = settings_field_names()

    missing = sorted(field_names - example_keys)
    extra = sorted(example_keys - field_names)

    if not missing and not extra:
        print(f"{ENV_EXAMPLE_PATH} is in sync with Settings.")
        return 0

    if missing:
        print("Missing from .env.example:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
    if extra:
        print("Unknown keys in .env.example (not in Settings):", file=sys.stderr)
        for name in extra:
            print(f"  - {name}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
