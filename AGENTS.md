# Agent Instructions

For repo architecture, service/endpoint changes, legacy/DGL migration, dependency
wiring, or request-flow debugging, use the repo-local skill as the source of
truth:

1. Read `.agents/fastapi-template-repo/SKILL.md`.
2. Read `.agents/fastapi-template-repo/references/architecture.md` when the task touches bootstrap, platform capabilities, business services, API dependency adapters, or migration boundaries.
3. Use codegraph first when available; otherwise fall back to `rg`, `sed`, `nl`, and focused tests.

Do not duplicate the architecture rules here. Update the repo-local agent skill first
so Codex, Claude, and other agents stay aligned.
