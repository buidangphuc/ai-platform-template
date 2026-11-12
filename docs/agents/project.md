# Project facts for agents

## Feedback loops
<!-- read by: diagnosing-bugs, tdd -->
- Without infra (CI): `make test` (`pytest -m "not infra"`)
- Everything on localinfra: `make infra-up` then `make test-infra`
- Eval gate: `make eval-ci`
- Layer rules: `make arch`
- Tests fake only the LLM and Langfuse; everything else runs on real services from localinfra. Tests using an infra fixture (`tests/infra.py`) get the `infra` marker automatically.
  - Start services: `make infra-up` (runs `bin/li up redis postgres mongo minio elasticmq rabbitmq` in `LOCALINFRA_DIR`, default `~/Documents/localinfra`; Postgres is `pgvector/pgvector:pg16`)
  - Run: `uv run --env-file .env.test pytest` (`.env.test` sets `TEST_*` URLs and `TEST_INFRA_REQUIRED=1`; a missing service then fails instead of skipping)
  - CI runs `pytest -m "not infra"` and never loads `.env.test`.

## Checks
<!-- read by: pre-commit-ci. Mirror CI exactly. -->
- Source: .github/workflows/test.yml (last read: 2026-11-12)
- `make verify` (runs `check typecheck arch hooks test-ci eval-ci`, the same targets CI calls)
- Local only, not in CI: `make infra-up && make test-infra` (all tests on real services, `--cov-fail-under=80`). Run it before every commit/push: CI cannot catch store, migration or queue regressions.

## Tracker
<!-- read by: to-tickets -->
- GitHub `buidangphuc/ai-platform-template`.
- No spec or change-proposal files live in this repo: it is a template that products clone. Plans go in GitHub issues and PR descriptions; behaviour is pinned by tests and described in `docs/`.

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
