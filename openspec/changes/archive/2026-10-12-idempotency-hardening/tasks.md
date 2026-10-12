## 1. Claim token

- [x] 1.1 `claim_token` column, set on claim and reclaim, returned as `IdempotencyClaim`. Verify: `test_check_or_store_creates_in_progress_record_for_new_key`, `test_check_or_store_reclaims_stuck_in_progress_record`
- [x] 1.2 `store_response` fenced on `claim_token` + `in_progress`. Verify: `test_late_original_with_identical_request_cannot_complete_the_retrys_claim`, `test_late_original_cannot_overwrite_reclaiming_retry`, `test_store_idempotency_response_is_a_fenced_update`
- [x] 1.3 `IdempotentCall` carries the token. Verify: `test_idempotency_boundary_stores_success_response_after_start`
- [x] 1.4 Migration `0007_idempotency_claim_token`. Verify: `alembic check` clean, downgrade/upgrade round-trip on Postgres 16

## 2. Retention

- [x] 2.1 `delete_expired(before, limit)` batched. Verify: `test_delete_expired_returns_row_count`, `test_delete_expired_purges_only_expired_rows_in_bounded_batches`
- [x] 2.2 Worker cleanup loop purges idempotency keys. Verify: `test_cleanup_loop_purges_expired_idempotency_keys_in_batches`
