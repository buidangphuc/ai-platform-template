## 1. CI workflow

- [x] 1.1 Rewrite `.github/workflows/test.yml` with lint, pytest and migrations jobs. Verify: `uvx pre-commit run check-yaml --files .github/workflows/test.yml`; each step's command run locally (migrations against a throwaway postgres:16 container).

## 2. Dead config and deps

- [x] 2.1 Delete `mypy.ini`. Verify: `rg mypy` finds no remaining references.
- [x] 2.2 Remove unused deps and add `pytest-cov` in `pyproject.toml` / `uv.lock`. Verify: `uv lock && uv sync --dev --all-extras && uv run --all-extras pytest -q`.

## 3. Pyright

- [x] 3.1 Narrow `last_messages` in `tests/unit/modules/test_evals_judge.py`. Verify: `uv run --all-extras pyright` reports 0 errors.

## 4. Docs

- [x] 4.1 Fix `ops/observability/README.md`. Verify: `tests/unit/core/test_config.py` pins that the setting is absent.
