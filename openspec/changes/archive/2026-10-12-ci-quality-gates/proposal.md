## Why

CI ran only `pytest` and the eval gate. The eval step crashed in CI because `Settings` requires `POSTGRES_*` and `REDIS_HOST` and no env was provided. Lint, type checking, coverage, pre-commit hooks and migrations were never gated, and dead config and dependencies had accumulated (`mypy.ini` targeting py3.10 with mypy not installed, unused packages, a documented `OBSERVABILITY_BACKEND` setting that does not exist).

## What Changes

- `.github/workflows/test.yml` split into `lint` (ruff format/check, pyright, pre-commit), `pytest` (coverage with `--cov-fail-under=80`, eval gate with `.env.example` loaded) and `migrations` (postgres:16 service, `alembic upgrade head`, advisory `alembic check`).
- Delete `mypy.ini`.
- Remove unused dependencies: `aiofiles`, `cachetools`, `fastapi-pagination`, `msgspec`, `numpy`, `pydantic-extra-types`; drop the duplicate core `motor` (kept in the `mongo` extra, where `app/core/mongo.py` imports it lazily). Add `pytest-cov` to the dev group.
- Fix the pyright `reportOptionalSubscript` error in `tests/unit/modules/test_evals_judge.py`.
- Correct `ops/observability/README.md` to match `Settings` (no `OBSERVABILITY_BACKEND`).

## Capabilities

None (tooling and docs only; no spec changes).

## Impact

CI only; no runtime code changes. `alembic check` currently reports drift (quota models not imported in `alembic/env.py`; tasks/outbox indexes not on the models), so that step is `continue-on-error` until fixed.
