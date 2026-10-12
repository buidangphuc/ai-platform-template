## 1. Poison-task cap

- [x] 1.1 `reclaim_stale_processing(now, limit, max_attempts)` fails tasks at the cap with `max_attempts_exceeded` instead of re-announcing (owns: messaging/tasks/{store,service,outbox,relay}.py, adapters/*); verify `test_reclaim_fails_a_task_that_used_up_its_attempts`, `test_poison_task_is_failed_without_a_new_outbox_event`

## 2. Retention

- [x] 2.1 Worker cleanup loop deletes expired tasks and old published outbox rows in batches (owns: tasks/relay.py, outbox/{store,adapters}.py, bootstrap/worker.py); verify `test_cleanup_loop_purges_expired_tasks_and_old_published_events_in_batches`, `test_delete_published_before_purges_only_old_published_rows_in_batches`
- [ ] 2.2 Schedule idempotency `delete_expired` (not done; separate change)

## 3. Schema

- [x] 3.1 Migration `0006_drop_quota_resv_idx` drops `ix_quota_reservations_subject_id`; verify `alembic check` clean and downgrade/upgrade round-trip on Postgres 16
