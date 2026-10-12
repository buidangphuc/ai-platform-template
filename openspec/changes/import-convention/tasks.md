## 1. Convention

- [x] 1.1 Move `Base` into `app/core/database/model.py` (owns: core/database/{engine,model}.py); verify with `pytest tests/unit/core/test_db_model.py`
- [x] 1.2 Rewrite re-export call sites to defining modules with an AST script (owns: alembic/env.py, bootstrap/{resources,worker}.py, */models.py, quota/records.py, tests/unit/core/test_{database,db_model}.py); verify with `ruff check` clean
- [x] 1.3 Empty the re-exporting `__init__.py` files and drop `__all__` (owns: the 4 `__init__.py` files, core/config/__init__.py, idempotency/http.py); verify with pyright error count unchanged (1 pre-existing, tests/unit/modules/test_evals_judge.py:47)
- [x] 1.4 Add `tests/unit/test_package_inits.py`; verify it fails on the old tree and passes now
- [x] 1.5 Update `app/core/README.md` and `.agents/fastapi-template-repo/SKILL.md`; verify by reading the docs

## 2. Verification

- [x] 2.1 Full `uv run --all-extras pytest -q` passes
