# How to work in this repo

## Architecture: source of truth

The architecture knowledge for this repo lives in the repo-local skills under `.agents/`. Read them before touching anything that involves understanding the repo, adding an endpoint/service, migrating legacy/DGL code, fixing wiring, or reviewing the platform/business/API boundary — they tell you where code lives and how it's wired, so you don't have to reverse-engineer it from scratch.

- Start with `.agents/fastapi-template-repo/SKILL.md` (where code lives, how wiring works).
- Read `.agents/fastapi-template-repo/references/architecture.md` when the task touches bootstrap, platform capability, business service, API dependency adapter, or legacy migration.
- Read `.agents/senior-ai-engineer/SKILL.md` when the task needs engineering judgment (designs with trade-offs, code review, debugging a flow) or touches LLM/model/prompt/RAG/eval/completions. It adds senior working discipline plus the repo's AI patterns, and is meant to be used alongside fastapi-template-repo, not instead of it. The AI details are in `.agents/senior-ai-engineer/references/ai-engineering.md`.

Keep these skills as the one place architecture rules live. Don't copy rules into `CLAUDE.md` — when a convention changes, edit the relevant skill under `.agents/` so there's a single source.

## Mapping code before you edit

Use the `codegraph` MCP tools to map flow and symbols before writing or editing code — it's a pre-built index, so `codegraph_context` first and then `codegraph_explore`/`codegraph_trace` answers most "how does X work / where is X" questions in a couple of calls. Fall back to `rg`, `sed`, `nl`, and focused tests when codegraph isn't available.

## Offloading context-heavy work to subagents

Some tasks generate a lot of raw output that would crowd out the main context window without adding lasting value. Hand those to a subagent via the `Agent` tool (`Explore` for read-only search, `general-purpose` for multi-step work), and keep only the distilled result. Good candidates:

- Reading and analyzing large raw log files (>1MB).
- Bulk extraction / parsing of text into a schema (e.g. JSON).
- Generating large volumes of mock data.
- Bulk text transformation (regex sweeps, format conversion) across many files.

Give the subagent a precise, self-contained task and ask it to return only the structured result you need. Its final message comes back as the tool result — relay what matters, not the raw dump.

## Keep in the main thread

- Editing code logic or architecture in `app/` — do it directly, with the `.agents/` skills as your guide.
- Reading small files (<500 lines) — just use `Read`.
- Anything that depends on the current code context you've built up — a subagent starts fresh and would lose that context.
