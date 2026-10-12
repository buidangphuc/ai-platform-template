## 1. Remove runtime_checkable

- [x] 1.1 Drop `@runtime_checkable` and its import (owns: messaging/{queue/gateway,tasks/service,tasks/store,outbox/publisher,outbox/store}.py, platform/{objects/gateway,quota/store,idempotency/store,cache/gateway}.py, bootstrap/addons.py, ai/evals/evaluators.py); verify with `rg runtime_checkable app` empty
- [x] 1.2 Rewrite or drop the 4 Protocol `isinstance` asserts (owns: tests/unit/modules/test_idempotency_store.py, tests/unit/modules/test_outbox.py, tests/unit/core/test_bootstrap_addons.py); verify with `pytest tests/unit/modules/test_outbox.py tests/unit/modules/test_idempotency_store.py tests/unit/core/test_bootstrap_addons.py`

## 2. Typed limiter lookup

- [x] 2.1 Use `get_app_resources(scope["app"]).ip_rate_limiter` in `IPRateLimitMiddleware._lookup_limiter` and add a lookup test (owns: app/core/middleware.py, tests/unit/modules/test_rate_limit.py); verify with `pytest tests/unit/modules/test_rate_limit.py`

## 3. Dead engine singleton

- [x] 3.1 Delete `_engine`, `_sessionmaker`, `get_sessionmaker`, `dispose_engine` and unused imports (owns: app/core/database/engine.py, app/core/database/__init__.py); verify with `rg "get_sessionmaker|dispose_engine" app tests scripts alembic` empty

## 4. Verification

- [x] 4.1 `ruff format`, `ruff check`, pyright (1 pre-existing error at tests/unit/modules/test_evals_judge.py:47) and `uv run --all-extras pytest -q` pass
