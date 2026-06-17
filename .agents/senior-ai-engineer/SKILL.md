---
name: senior-ai-engineer
description: Work like a senior AI software engineer in this FastAPI backend — understand before changing, weigh trade-offs, and ship AI features safely. Use this skill whenever the task touches LLM/model calls, prompts, RAG, evals, fallbacks, or the completions pipeline, AND for any non-trivial change that needs design judgment, failure-mode thinking, debugging a model/flow, or code review — even if the user doesn't say "be senior" or name a file. Adds engineering discipline and this repo's AI/LLM patterns on top of fastapi-template-repo (architecture) and codegraph (the map); pair it with them, don't replace them.
---

# Senior AI Engineer

This skill shapes *how* you work on this repo, not *where* code lives.

- For repo structure, layer boundaries, and "where does this go" → use
  `fastapi-template-repo` (architecture facts). Do not duplicate them here.
- For the live map of symbols and flows → use codegraph first.
- This skill adds two things on top: **senior engineering discipline** (how a
  strong engineer approaches a change) and **AI/LLM engineering patterns**
  specific to this codebase.

Always pair this skill with `fastapi-template-repo`; they are complementary.

## Operating Principles

Apply all of these; they are the difference between a junior diff and a senior one.

1. **Understand before you change.** Restate the problem in one sentence. Map
   the flow with codegraph (fall back to `rg`/`sed`/`nl`) and locate the exact
   layer boundary you will touch *before* editing. Never edit a file you have
   not read.
2. **Smallest correct change.** Prefer the repo's existing patterns over new
   abstractions. Do not add layers, configs, or generality "for later". If you
   are tempted to abstract, you need two real call sites first.
3. **Design when it is non-trivial.** For anything beyond a local edit, state
   the approach, the main alternative you rejected, and *why*. Name the
   trade-off (latency vs cost, simplicity vs flexibility, etc.) explicitly.
4. **Make failure modes explicit** — this matters most for AI calls. Every
   external/model call needs a bounded timeout, a fallback or circuit-breaker
   path, and a defined behavior on partial failure. Never assume the happy path.
5. **Tests are part of the change, not after it.** Unit test the service
   behavior and failure modes; integration test the API contract. Run the
   narrow check first, widen after touching bootstrap/platform/public API.
6. **Communicate like a reviewer would want.** When you finish, say what
   changed, what you deliberately did *not* change, the assumptions you made,
   and what is risky or unverified. No false "done and verified".
7. **Know when to stop and ask.** Ambiguous contract, irreversible action
   (data/schema/external side effect), or a security-sensitive choice → surface
   it instead of guessing.

## AI / LLM Engineering (short version)

Load `references/ai-engineering.md` before building or changing any LLM, RAG,
eval, or completions feature. The non-negotiables:

- **Go through the platform, not the SDK.** Business code receives an
  `LLMInstance` (`app/modules/ai/llm/runtime.py`) or a model handler as a
  constructor dependency. It must never call `init_chat_model` / construct a
  provider client itself. Model choice and fallback live in `ModelRouter`.
- **Three things every AI feature must have:** observability (Langfuse trace via
  `LLMInstance.trace_config(...)`), resilience (timeout + breaker/fallback from
  `app/core/resilience`), and an **eval story** (cases + evaluators, see
  `app/modules/ai/evals`).
- **Treat prompts as code and evals as tests.** A prompt or model change is a
  behavior change — it needs eval cases that gate or monitor it, not just a
  manual spot check.
- **Redact before you log or trace.** Use `RedactionPolicy`
  (`app/core/redaction`) for any sensitive model input/output.
- RAG and completions already have patterns (factory addon; Protocol ports +
  pipeline). Extend them; do not invent parallel ones.

## Workflow For An AI Feature

1. codegraph the area; confirm the boundary with `fastapi-template-repo`.
2. Decide where the dependency lives: app-lifetime (LLM instance, RAG service →
   bootstrap + `ApplicationResources`) vs request-scoped.
3. Implement business logic in the owning `app/modules/business/<domain>`,
   taking the model/handler as a constructor dependency.
4. Wire observability + resilience + redaction at the call site.
5. Add or update eval cases; pick inline gating or async monitoring (Pattern A/B
   in `references/ai-engineering.md`).
6. Add the API dependency adapter and keep the endpoint thin.
7. Verify (below). State assumptions and risk in your summary.

## Verification Defaults

Narrow first, then widen:

- `uv run ruff check app tests`
- `uv run pyright`
- focused pytest for the touched module/API
- full `uv run pytest` after bootstrap, platform, or public API changes
- for AI behavior: run the relevant eval cases; tests run against
  `FakeListChatModel` (no provider keys) unless the user wants real calls.

## Delegation

Follow `CLAUDE.md`: offload bulk/log/extraction/mock-data work to a subagent via
the `Agent` tool and keep only the distilled result; keep architecture and code
logic in `app/` here. Use codegraph as the first map, verify stale entries with
direct reads.
