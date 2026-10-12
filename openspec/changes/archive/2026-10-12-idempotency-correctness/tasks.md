## 1. Service and adapter

- [x] 1.1 Row-locked conflict read, `updated_at` refresh on reclaim. Verify: `tests/unit/modules/test_idempotency_postgres_store.py::test_concurrent_retries_of_a_stuck_key_reclaim_it_once`, `::test_concurrent_retries_of_an_expired_key_reclaim_it_once`, `test_idempotency_store.py::test_conflict_path_reads_the_record_under_a_row_lock`
- [x] 1.2 Fenced `store_idempotency_response` / `store_response` returning `bool`. Verify: `test_late_original_cannot_overwrite_reclaiming_retry`, `test_completed_response_is_not_overwritten`, `test_store_idempotency_response_is_a_fenced_update`, `test_store_idempotency_response_reports_fenced_off_write`
- [x] 1.3 Typed `rowcount` in `delete_expired_idempotency_keys`. Verify: `test_delete_expired_returns_row_count`, pyright

## 2. Settings

- [x] 2.1 In-progress timeout default 600 in `app/core/config/platform.py` and `.env.example`. Verify: `test_build_idempotency_store_uses_postgres_adapter`, `check-env-example`

## 3. HTTP helper

- [x] 3.1 `IdempotentCall` handle replaces `request.state` handoff. Verify: `tests/unit/modules/test_idempotency_http.py::test_idempotency_boundary_stores_success_response_after_start`
