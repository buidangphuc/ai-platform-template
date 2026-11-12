# AGENTS.md

Minimal-core FastAPI template; every capability is opt-in behind a `*_ENABLED` flag.

## Commands

- `make dev`: run the server with autoreload
- `make test`: unit and integration tests, no infra (about 20 s)
- `make verify`: exactly what CI runs
- `make test-infra`: tests on real services (`make infra-up` first)
- `make new-domain NAME=<snake_case>`: scaffold a business domain
- `make help`: every target

## Read before you touch

| Touching | Read |
| --- | --- |
| `app/bootstrap`, `app/api`, a new feature or endpoint | `docs/agents/architecture.md` |
| `app/modules/ai`, prompts, evals, RAG | `docs/agents/ai-engineering.md` |
| checks, feedback loops, tracker | `docs/agents/project.md` |
| enabling a capability, fork steps | `docs/template-guide.md` |

## Hard rules

- New domain: run `make new-domain`, then edit. Never hand-wire `resources.py`, `services.py`, `api/router.py`, `worker.py` or `alembic/env.py`.
- Endpoints never build clients, stores or LLMs; business services never read `Request` or `app.state`.
- `__init__.py` files stay empty.
- A new Settings field goes into `.env.example` (checked).
- Tests fake only the LLM and Langfuse.
- Layer imports are enforced by `make arch`.
- Done means `make verify` is green.
