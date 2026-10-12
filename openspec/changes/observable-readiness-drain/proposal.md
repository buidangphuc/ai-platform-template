## Why

On SIGTERM uvicorn closes its listener immediately and only then runs lifespan
shutdown. The app marks `/readyz` 503 while draining (`streaming-observability`),
but no client can ever observe it: the socket already refuses connections, so load
balancers keep routing until connect errors start.

## What Changes

- New entry `python -m app.serve` runs uvicorn programmatically with a `uvicorn.Server`
  subclass. The first SIGTERM/SIGINT calls the existing `HealthService.begin_draining()`
  (`/readyz` 503), keeps the listener open for `SHUTDOWN_READINESS_DELAY_SECONDS`, then
  runs uvicorn's normal graceful shutdown. A second signal skips the wait and forces exit.
- New setting `SHUTDOWN_READINESS_DELAY_SECONDS` (float, `>= 0`, default 5, `0` disables).
- Dockerfile `CMD` becomes `["python", "-m", "app.serve"]` (exec form, PID 1 gets signals).
  Host/port come from `SERVER_HOST` / `SERVER_PORT` (default `0.0.0.0:8000`); loop, http,
  no access log and graceful timeout stay as before.
- README documents the Kubernetes implications.

## Impact

Spec delta: `core/health-drain`. Code: `app/serve.py`, `app/core/config/runtime.py`,
`.env.example`, `Dockerfile`, `README.md`. Deployments that overrode the container
command to run `uvicorn main:app` keep the old behaviour (no delay).
