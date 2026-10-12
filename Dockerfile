# syntax=docker/dockerfile:1.7

# Build stage: resolve deps into an isolated virtualenv
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
# Opt-in optional extras (e.g. --build-arg UV_EXTRAS=ai, or "ai aws").
# Defaults to empty so the minimal-core image stays small.
ARG UV_EXTRAS=""
RUN --mount=type=cache,target=/tmp/uv-cache \
    uv sync --frozen --no-dev --no-install-project \
    $(for e in $UV_EXTRAS; do printf -- '--extra %s ' "$e"; done)

# Runtime stage: minimal image, non-root, healthcheck
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /app --shell /sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app main.py alembic.ini ./

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).status == 200 else 1)"

# Exec form: python is PID 1 and receives SIGTERM. app.serve marks /readyz 503 on
# SIGTERM, keeps the listener open SHUTDOWN_READINESS_DELAY_SECONDS, then runs
# uvicorn's graceful shutdown (GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS). Host/port come
# from SERVER_HOST / SERVER_PORT (default 0.0.0.0:8000).
CMD ["python", "-m", "app.serve"]
