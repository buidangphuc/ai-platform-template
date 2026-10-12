## Why

Some checks exist only because the code around them is not clean: `@runtime_checkable` on Protocols that
nothing checks at runtime, a middleware lookup that guards against `app.state.resources` being absent (`create_app`
always sets it), and a module-level engine singleton with no callers. Each one hides the real contract and
adds branches to read.

## What Changes

- Remove every `@runtime_checkable` decorator (and its import) from the Protocol files in `app/`. Nothing in
  `app/` calls `isinstance` on these Protocols. Tests that asserted a Protocol now assert the concrete class
  or are dropped when pyright already guarantees the type.
- `IPRateLimitMiddleware._lookup_limiter` uses `get_app_resources(scope["app"]).ip_rate_limiter` instead of
  `scope.get("app")` / `getattr` / `is None` guards. The caller keeps its single `limiter is None` no-op check
  (feature off is legitimate). Add a test covering the lookup.
- Delete the dead singleton in `app/core/database/engine.py`: `_engine`, `_sessionmaker`, `get_sessionmaker`,
  `dispose_engine`, and the re-exports in `app/core/database/__init__.py`. Bootstrap owns the engine lifecycle.

## Capabilities

### New Capabilities

None. Pure refactor; `skip_specs: true`.

## Impact

- No runtime behavior change on the supported paths.
- `isinstance(x, <Protocol>)` no longer works for these Protocols; only tests used it.
- `app.core.database.get_sessionmaker` and `dispose_engine` are gone (zero callers).
