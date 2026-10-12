## Why

The repo root mixes product files with tool leftovers and per-tool configs, and agent instructions are duplicated across `CLAUDE.md`, `AGENTS.md` and `.agents/` skills. The owner now keeps agent behaviour in user-level instructions, which already say project facts live in `docs/agents/project.md`.

- Root clutter: `pyrightconfig.json`, `.nbqa.ini` (no hook uses nbqa), stale `requirements.txt` (repo uses uv; it lists dead deps), `docker-compose.local.yaml`, `docker-compose.langfuse.yaml`, `.env.langfuse.example`, `TEMPLATE_GUIDE.md`.
- Unused AI tooling: Spec Kit (`.specify/`, `.claude/skills/speckit-*`) replaced by OpenSpec; `.claude/settings.json`; `docs/superpowers/` (old plugin plans).
- `README.md` (391 lines) holds usage how-tos (env defaults table, auth, docker, commands) instead of a basic repo overview.

## What Changes

- Root keeps only: `.env.example`, dotfiles (`.dockerignore`, `.editorconfig`, `.gitignore`, `.pre-commit-config.yaml`, `.secrets.baseline`), `Dockerfile`, `Makefile`, `README.md`, `alembic.ini`, `main.py`, `pyproject.toml`, `uv.lock`, and the source dirs.
- Pyright config moves to `[tool.pyright]` in `pyproject.toml`; `.nbqa.ini` and `requirements.txt` are deleted.
- Compose stack moves to `ops/compose/`: `local.yaml`, `langfuse.yaml`, `langfuse.env.example`. `make docker-run` / `make docker-run-langfuse` keep working unchanged for the user.
- `.agents/` becomes plain docs in `docs/agents/` (`architecture.md`, `ai-engineering.md`) plus `docs/agents/project.md` (feedback loops, checks, tracker, docs, hot paths). `CLAUDE.md`, `AGENTS.md`, `.agents/`, `.specify/`, `.claude/`, `docs/superpowers/` are deleted; `.claude/` is gitignored.
- `README.md` becomes a short overview (what it is, scope, layout, minimal quickstart, links). Usage moves to `docs/usage.md`; `TEMPLATE_GUIDE.md` moves to `docs/template-guide.md`. Instruction files point to paths instead of repeating content.

No runtime or HTTP behaviour changes.

## Impact

Paths for compose files, the Langfuse env example and agent docs change. `make` targets, CI jobs and settings names stay the same.
