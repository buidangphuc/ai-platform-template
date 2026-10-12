## Why

Package `__init__.py` files re-exported symbols with `__all__`, so importing one name loaded the whole
package. Every ORM model imported `Base` via `app.core.database`, which also loaded `engine.py` and with it
FastAPI and `app.bootstrap.state`, a cycle risk with bootstrap. This change goes first because the later
bootstrap changes rewrite these same imports.

## What Changes

- Package `__init__.py` files hold no code (a docstring is allowed) and no `__all__`. This covers
  `core/database`, `platform/mongo`, `messaging/tasks` and `messaging/queue`.
- Drop `__all__` from `core/config/__init__.py`, which still defines `Settings`, and from
  `platform/idempotency/http.py`.
- Move `Base` from `core/database/engine.py` to `core/database/model.py`, so models no longer load the engine.
- Call sites import each symbol from its defining file (app, tests, alembic).
- Add `tests/unit/test_package_inits.py` to enforce the rule. Document it in
  `.agents/fastapi-template-repo/SKILL.md` and `app/core/README.md`.
- No runtime behavior changes.

## Capabilities

### New Capabilities

None. Pure refactor; `skip_specs: true`.

### Modified Capabilities

None.

## Impact

Import paths change for internal callers only. No public API changes. Historical docs under
`docs/superpowers/` are left as written.
