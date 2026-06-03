---
name: fastapi-template-repo
description: Understand and modify this FastAPI template repository with a codegraph-first workflow. Use for repo architecture questions, adding endpoints or business services, migrating legacy/DGL code, reviewing dependency wiring, debugging request-to-service flows, or any task that asks how this backend is structured.
---

# FastAPI Template Repo

This repo-local agent skill is the canonical AI instruction for this backend.
Codex, Claude, and other agents should read it through the repo instructions in
`AGENTS.md` and `CLAUDE.md`.

## Core Workflow

1. Start with `mcp__codegraph.codegraph_context` for architecture, flow, bug, or feature tasks when the tool is available.
2. If codegraph reports stale entries or misses the target, verify with `rg` and direct file reads.
3. Keep the layer boundary visible before editing:
   - API routers parse HTTP input and call a business service.
   - Business services receive explicit constructor dependencies.
   - Platform modules expose reusable capabilities and backend factories.
   - Bootstrap opens platform resources and composes app services.
4. Prefer the repo's existing patterns over new abstractions.
5. Verify with focused tests first, then broader checks when bootstrap, platform, or API contracts change.

## Codegraph Usage

Use codegraph as the first map, not the only source of truth.

- Use `codegraph_context` for "how does this work?", "where should this go?", endpoint flow, service wiring, and bug reports.
- Use `codegraph_trace` when the user asks how one symbol reaches another.
- Use `codegraph_search` only for quick symbol discovery.
- If the response says files are stale or pending sync, inspect those exact files with `rg`, `sed`, or `nl` before deciding.
- Do not re-read files already fully included by codegraph unless you need fresher content or surrounding lines.
- If the current agent does not have codegraph tools, fall back to `rg`, `sed`, `nl`, and focused tests.

## Repository Rules

Load `references/architecture.md` when adding services/endpoints, changing bootstrap wiring, reviewing platform-vs-business boundaries, or migrating legacy code.

Short version:

- `app/api`: transport/controller layer.
- `app/bootstrap`: app factory, lifespan resources, and central service composition.
- `app/modules/platform`: reusable capabilities such as Mongo, quota, cache, objects, rate limit, idempotency, queues.
- `app/modules/business`: domain/product logic only.
- `app/core`: settings, infra primitives, health, errors, middleware.

Avoid:

- Business services reading `Request`, `app.state`, or global service locators.
- Endpoint files constructing stores, HTTP clients, LLMs, quota stores, or dependency graphs.
- Product-specific setup inside `app/modules/platform`.
- Generic `deps.py` files that collect unrelated feature wiring.

## Adding Or Changing A Service

Use this sequence:

1. Define or update the business service in `app/modules/business/<domain>/services`.
2. Keep stores and external integrations as constructor dependencies.
3. If runtime dependencies must be opened once per app lifecycle, wire them in bootstrap from already-open platform resources.
4. Register app-composed services in `ApplicationResources.services`.
5. Add a small API dependency adapter under the owning API surface, for example `app/api/<surface>/dependencies.py`.
6. Endpoint functions should parse HTTP input, call one service method, and return the existing response contract.
7. Add unit tests for service behavior and integration tests for API contract.

Adding a new endpoint usually should not touch bootstrap. Touch bootstrap only when the endpoint introduces a new app-level service or a new lifecycle-owned runtime dependency.

## Verification Defaults

Run the narrowest useful checks, then widen:

- `uv run ruff check app tests`
- `uv run pyright`
- focused pytest for touched module/API
- full `uv run pytest` after bootstrap, platform, or public API changes

For Docker smoke checks, prefer a minimal local runtime with disabled external AI dependencies unless the user explicitly wants real provider calls.
