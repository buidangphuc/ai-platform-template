# Project facts for agents

## Feedback loops
<!-- read by: diagnosing-bugs, tdd -->
- Unit/integration: `uv run --all-extras pytest -q`
- Eval gate: `uv run --env-file .env.example --all-extras python -m scripts.run_eval --min-score 0.8`
- Real-infra tests are env-gated. Fakes hid real bugs, so adapter/lifecycle changes also run these:
  - `TASKS_TEST_POSTGRES_URL`, `IDEMPOTENCY_TEST_POSTGRES_URL`, `QUOTA_TEST_POSTGRES_URL` (postgres+asyncpg; alembic also needs `REDIS_HOST`)
  - `REAL_REDIS_URL` with `-p tests.plugins.real_redis`
  - `QUOTA_TEST_MONGO_URI`
  - `S3_TEST_ENDPOINT_URL` (LocalStack)
  - `SQS_TEST_ENDPOINT_URL` (ElasticMQ)

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
- `uv run --no-dev --env-file .env.example python -c "import main, scripts.run_worker; print('ok')"` (after `uv sync --frozen --no-dev`)
- `uv run --all-extras alembic upgrade head` then `uv run --all-extras alembic check` (needs `POSTGRES_*`, `REDIS_HOST`)

## Tracker
<!-- read by: to-tickets -->
- GitHub `buidangphuc/ai-platform-template`.
- Changes are planned as OpenSpec changes under `openspec/changes/` (archived to `openspec/changes/archive/`, specs in `openspec/specs/`).

## Docs
<!-- read by: domain-modeling, research -->
- Architecture: `docs/agents/architecture.md` (read before touching bootstrap/platform/business/API boundaries or adding a feature)
- AI: `docs/agents/ai-engineering.md` (LLM/prompt/RAG/eval/completions)
- ADRs: `docs/adr/`
- Usage: `docs/usage.md`
- Template guide: `docs/template-guide.md`

## Hot paths
<!-- read by: everyone. Things that look alike but must not be confused. -->
- `app.state.resources` is the deliberate controller seam: views read services there.
- `app/core/telemetry.py` (no OTel import) vs `app/core/telemetry_otel.py` (optional extra).
- `.env.example` is checked against Settings by `scripts/check_env_example.py`.
