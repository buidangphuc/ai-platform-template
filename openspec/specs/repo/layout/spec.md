# repo/layout Specification

## Purpose
Where repository-level configuration, ops files and documentation live, so the root stays small and every document has one home.

## Requirements

### Requirement: Small repository root

The repository root SHALL hold only `.env.example`, standard dotfiles, `Dockerfile`, `Makefile`, `README.md`, `alembic.ini`, `main.py`, `pyproject.toml`, `uv.lock` and source directories. Tool configuration SHALL live in `pyproject.toml` when the tool supports it.

#### Scenario: Root listing
- **WHEN** listing tracked files at the repository root
- **THEN** no `pyrightconfig.json`, `.nbqa.ini`, `requirements.txt`, `docker-compose.*.yaml`, `.env.langfuse.example`, `TEMPLATE_GUIDE.md`, `CLAUDE.md` or `AGENTS.md` exists

#### Scenario: Checks unchanged
- **WHEN** running `uv run --all-extras pyright`, the test suite and `make docker-run` / `make docker-run-langfuse`
- **THEN** they behave as before the move

### Requirement: Agent docs are plain project docs

Architecture and AI-engineering conventions SHALL live in `docs/agents/` as plain Markdown, indexed by `docs/agents/project.md`. The repository SHALL contain no agent-specific instruction files or tool directories (`CLAUDE.md`, `AGENTS.md`, `.agents/`, `.claude/`, `.specify/`).

#### Scenario: Agent finds conventions
- **WHEN** an agent reads `docs/agents/project.md`
- **THEN** its `## Docs` section points to `docs/agents/architecture.md` and `docs/agents/ai-engineering.md`

### Requirement: README is an overview

`README.md` SHALL explain what the repo is, its scope, its layout and a minimal quickstart, and link to `docs/usage.md`, `docs/template-guide.md` and `docs/agents/project.md` for details. Usage how-tos SHALL live in `docs/`, not in `README.md`.

#### Scenario: No usage tables in README
- **WHEN** reading `README.md`
- **THEN** it holds no per-variable env table, auth walkthrough or command reference; those are in `docs/usage.md`
