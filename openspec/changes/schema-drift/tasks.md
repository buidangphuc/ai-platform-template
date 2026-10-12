## 1. Schema

- [x] 1.1 Align models with migrations and add CHECKs, partial index, migration 0005. Verify: `alembic upgrade head && alembic check` on postgres:16 reports no new upgrade operations; `downgrade -1 && upgrade head` round-trips.

## 2. CI

- [x] 2.1 Make the `alembic check` step blocking. Verify: `uvx pre-commit run check-yaml --files .github/workflows/test.yml`.
