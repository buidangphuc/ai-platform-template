Branch: `chore/repo-tidy`. Sonnet worktree agents write all changes (skill `openspec-fanout`). All three packets run in wave 1.

Shared contract (all packets use these final paths):
- `ops/compose/local.yaml`, `ops/compose/langfuse.yaml`, `ops/compose/langfuse.env.example` (was `docker-compose.local.yaml`, `docker-compose.langfuse.yaml`, `.env.langfuse.example`); `make docker-run`, `make docker-run-langfuse`, `make docker-build` keep their names; a local `.env.langfuse` at the root is still picked up.
- `docs/agents/project.md`, `docs/agents/architecture.md`, `docs/agents/ai-engineering.md`.
- `docs/usage.md`, `docs/template-guide.md`.

## 1. Root config and tooling cleanup

Owns: `pyproject.toml`, delete `pyrightconfig.json`, `.nbqa.ini`, `requirements.txt`; move `docker-compose.local.yaml`, `docker-compose.langfuse.yaml`, `.env.langfuse.example` to `ops/compose/`; `Makefile`; `.pre-commit-config.yaml`; `.gitignore`; `.dockerignore`; `Dockerfile` (only if a path changes); `tests/unit/core/test_config.py` (only the `.env.langfuse.example` path); delete `.specify/`, `.claude/`.

- [x] 1.1 `[tool.pyright]` in `pyproject.toml` with identical settings; delete `pyrightconfig.json`; verify `uv run --all-extras pyright` → 0 errors, same file count checked
- [x] 1.2 Delete `.nbqa.ini`, `requirements.txt`; verify `rg -n "nbqa|requirements.txt"` outside `openspec/changes/archive` is empty
- [x] 1.3 Move compose files and Langfuse env example; fix relative paths inside them (build context, env files, mounted files like `ops/observability/*`) and the Makefile targets (`--project-directory .` or adjusted paths); verify `docker compose --project-directory . -f ops/compose/local.yaml -f ops/compose/langfuse.yaml config -q` succeeds, and `tests/unit/core/test_config.py` passes with the new path
- [x] 1.4 Delete `.specify/`, `.claude/`; add `.claude/` to `.gitignore`; drop `.specify/` and `.claude/skills/` excludes from `.pre-commit-config.yaml`; verify `uv run pre-commit run --all-files`

## 2. Agent docs to docs/agents

Owns: `.agents/**` (delete), new `docs/agents/{project,architecture,ai-engineering}.md`, delete `CLAUDE.md`, `AGENTS.md`, `docs/superpowers/**`; `openspec/config.yaml`; `docs/migration/phase-log.md` and `docs/adr/*.md` (links only).

- [x] 2.1 `docs/agents/architecture.md` = `.agents/fastapi-template-repo/SKILL.md` + `references/architecture.md` merged into one plain doc (no skill frontmatter, no "use this skill when" text, no duplicated rules); `docs/agents/ai-engineering.md` = `.agents/senior-ai-engineer/SKILL.md` + `references/ai-engineering.md` likewise. Content rules unchanged.
- [x] 2.2 `docs/agents/project.md` in the setup-project format (sections: Feedback loops, Checks, Tracker, Docs, Hot paths), Checks mirroring `.github/workflows/test.yml`; Docs pointing to the two docs above, `docs/adr/`, `openspec/`; content as paths, not repeated rules
- [x] 2.3 Delete `.agents/`, `CLAUDE.md`, `AGENTS.md`, `docs/superpowers/`; fix links in `openspec/config.yaml`, `docs/migration/phase-log.md`, `docs/adr/`; verify `rg -n "\.agents/|CLAUDE\.md|AGENTS\.md|superpowers"` outside `openspec/changes/archive` is empty

## 3. README and usage docs

Owns: `README.md`, move `TEMPLATE_GUIDE.md` to `docs/template-guide.md`, new `docs/usage.md`.

- [x] 3.1 `README.md` ≤ ~120 lines: what it is, scope, minimal core vs opt-in capabilities (short), project layout (with the new paths), minimal quickstart, links to `docs/usage.md`, `docs/template-guide.md`, `docs/agents/project.md`, `openspec/`
- [x] 3.2 `docs/usage.md` takes the README's usage material verbatim-in-substance (requirements, full quickstart, docker with new compose paths, local commands, secrets, env defaults, bearer auth); `docs/template-guide.md` = `TEMPLATE_GUIDE.md` with links fixed; verify every relative link in the three files resolves
