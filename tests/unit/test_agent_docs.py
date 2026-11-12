import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = [
    path
    for path in [ROOT / "AGENTS.md", *sorted((ROOT / "docs" / "agents").glob("*.md"))]
    if path.exists()
]
PATH_PREFIXES = (
    "app/",
    "tests/",
    "scripts/",
    "docs/",
    "ops/",
    "alembic/",
    "evals/",
    ".github/",
)
BACKTICKED = re.compile(r"`([^`\n]+)`")
MAKE_TARGET = re.compile(r"\bmake ([a-z][a-z0-9_-]*)")
MAKEFILE_TARGET = re.compile(r"^([a-zA-Z0-9_-]+):", re.MULTILINE)


def _repo_paths(text: str) -> list[str]:
    paths = []
    for token in BACKTICKED.findall(text):
        if not token.startswith(PATH_PREFIXES):
            continue
        if any(mark in token for mark in ("<", "*", "...", " ")):
            continue
        paths.append(token.split(":", 1)[0])
    return paths


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_documented_paths_exist(doc: Path) -> None:
    missing = [p for p in _repo_paths(doc.read_text()) if not (ROOT / p).exists()]
    assert missing == []


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: path.name)
def test_documented_make_targets_exist(doc: Path) -> None:
    defined = set(MAKEFILE_TARGET.findall((ROOT / "Makefile").read_text()))
    mentioned = set(MAKE_TARGET.findall(doc.read_text()))
    assert sorted(mentioned - defined) == []
