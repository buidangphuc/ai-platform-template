## 1. API-key authentication

- [x] 1.1 `AUTH_API_KEYS` parsing, boot validation and production weak-digest check; verify `test_malformed_auth_api_keys_fail_fast`, `test_production_rejects_api_keys_hashing_a_known_weak_token`
- [x] 1.2 Constant-time match across all keys, shared-subject rotation, empty default scopes; verify `test_authenticate_compares_against_every_key_without_early_exit`, `test_several_keys_may_share_a_subject_for_overlap_rotation`
- [x] 1.3 `scripts/hash_api_key.py`; verify `test_generate_prints_a_token_and_a_digest_that_parses_as_an_api_key`

## 2. Task ownership

- [x] 2.1 `principal_id` on `TaskRecord`/`Task`, owner-scoped `get` in memory/redis/postgres, `require_owned`, API wiring; verify the conformance `test_get_scoped_to_principal_hides_other_owners_tasks` on every adapter and `test_task_poll_is_scoped_to_the_submitting_principal`
- [x] 2.2 Migration `0008_task_principal_id`; verify `alembic check` clean and downgrade/upgrade round-trip on Postgres 16
