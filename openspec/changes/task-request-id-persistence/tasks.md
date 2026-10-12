## 1. Persist and re-announce the request id

Owns: `app/modules/messaging/tasks/**`, `alembic/versions/0009_task_request_id.py`

- [x] 1.1 `request_id` on `TaskRecord`/`TaskRef`, all adapters, migration `0009`; verify `test_request_id_round_trips_and_defaults_to_none`, `test_reclaim_returns_the_submitting_request_id` (memory, SQLite/Postgres, Redis)
- [x] 1.2 Dispatchers announce it on submit and reclaim; verify `test_submit_persists_the_request_id_on_the_task`, `test_reclaimed_task_is_announced_with_its_original_request_id`, `test_reclaimed_task_is_reannounced_with_its_original_request_id` (outbox, SQLite and real Postgres)
