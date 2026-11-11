# Project facts for agents

## Feedback loops
<!-- read by: diagnosing-bugs, tdd -->
- Unit/integration: `uv run --all-extras pytest -q`
- Eval gate: `uv run --env-file .env.example --all-extras python -m scripts.run_eval --min-score 0.8`
- Tests fake only the LLM and Langfuse; everything else runs on real services from localinfra. Tests using an infra fixture (`tests/infra.py`) get the `infra` marker automatically.
  - Start services: `cd ~/Documents/localinfra && bin/li up core postgres mongo minio elasticmq rabbitmq`
  - Run: `uv run --env-file .env.test pytest` (`.env.test` sets `TEST_*` URLs and `TEST_INFRA_REQUIRED=1`; a missing service then fails instead of skipping)
  - CI runs `pytest -m "not infra"` and never loads `.env.test`.

## Checks
<!-- read by: pre-commit-ci. Mirror CI exactly. -->
- Source: .github/workflows/test.yml (last read: 2026-10-12)
- `uv sync --dev --all-extras`
- `uv run ruff format --check app tests scripts alembic`
- `uv run ruff check app tests scripts alembic`
- `uv run --all-extras pyright`
- `SKIP=commitizen uv run pre-commit run --all-files --hook-stage pre-commit`
- `uv run --all-extras pytest -q --cov=app --cov-report=term-missing --cov-fail-under=80`
- `uv run --env-file .env.example --all-extras python -m scripts.run_eval --min-score 0.8`

## Tracker
<!-- read by: to-tickets -->
- GitHub `buidangphuc/ai-platform-template`.
- Changes are planned as OpenSpec changes under `openspec/changes/` (archived to `openspec/changes/archive/`, specs in `openspec/specs/`).

## Docs
<!-- read by: domain-modeling, research -->
- Architecture: `docs/agents/architecture.md` (read before touching bootstrap/platform/business/API boundaries or adding a feature)
- AI: `docs/agents/ai-engineering.md` (LLM/prompt/RAG/eval/completions)
- Usage: `docs/usage.md`
- Template guide: `docs/template-guide.md`

## Hot paths
<!-- read by: everyone. Things that look alike but must not be confused. -->
- `app.state.resources` is the deliberate controller seam: views read services there.
- `app/core/telemetry.py` (no OTel import) vs `app/core/telemetry_otel.py` (optional extra).
- `.env.example` is checked against Settings by `scripts/check_env_example.py`.
