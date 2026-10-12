## 1. Mongo client and store

- [x] 1.1 `tz_aware=True, tzinfo=UTC` in `app/core/mongo.py`. Verify: `tests/unit/modules/test_quota_mongo_store.py::test_build_mongo_client_is_tz_aware`
- [x] 1.2 `ensure_indexes` + duplicate-key-safe reserve in `app/modules/platform/quota/adapters/mongo.py`. Verify: `test_ensure_indexes_declares_unique_partial_and_ttl_indexes`, `test_reserve_same_idempotency_key_returns_existing_without_leak`
- [x] 1.3 Atomic counter migration (same file). Verify: `test_migration_moves_usage_once_under_concurrency`
- [x] 1.4 Conditional-write refund/finalize (same file). Verify: `test_refund_concurrent_decrements_counter_once`, `test_concurrent_refund_and_finalize_has_single_winner`

## 2. Postgres store

- [x] 2.1 Conditional-write refund/finalize in `app/modules/platform/quota/adapters/postgres.py`. Verify: `tests/unit/modules/test_quota_postgres_store.py::test_concurrent_refund_decrements_exactly_once` (needs `QUOTA_TEST_POSTGRES_URL`)
- [x] 2.2 `ON CONFLICT DO NOTHING RETURNING` reserve. Verify: `test_concurrent_same_idempotency_key_returns_existing`, `test_reserve_over_limit_leaves_no_reservation_row`
- [x] 2.3 Upsert sets `updated_at` and uses `quota_limit`. Verify: `test_upsert_refreshes_updated_at`

## 3. Alembic

- [x] 3.1 Import quota records in `alembic/env.py`. Verify: `test_alembic_env_imports_quota_records`

## 4. Follow-up (other packet)

- [ ] 4.1 Wave 2 bootstrap calls `MongoQuotaStore.ensure_indexes` at open
