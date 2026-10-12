## Why

1. Authentication was one static `AUTH_BEARER_TOKEN`: every caller was the same
   principal (`AUTH_SUBJECT`) holding `AUTH_ROLES` (default `admin`). Rotation
   meant a flag-day, per-principal rate limiting limited nobody in particular,
   and the default granted admin implicitly.
2. Tasks stored no owner. `GET /completions/tasks/{id}` returned any task to any
   authenticated caller (BOLA / IDOR).

## What Changes

- **API keys (BREAKING).** `AUTH_BEARER_TOKEN`, `AUTH_SUBJECT`, `AUTH_ROLES` are
  removed. New `AUTH_API_KEYS`: comma-separated `subject:scope|scope:sha256hex`
  entries (subject = text before the first `:`, digest = text after the last;
  scopes may contain `:` and default to none). The presented token is hashed and
  compared with `hmac.compare_digest` against every entry (no early exit). Several
  entries may share a subject, which is how overlap rotation works. Parsing is
  eager: a malformed entry fails at boot in every environment. Outside
  dev/local/test at least one key is required, and production rejects a key whose
  digest is a known placeholder token (`WEAK_AUTH_DIGESTS`); token length cannot
  be checked because only hashes are configured. No compatibility path for
  `AUTH_BEARER_TOKEN`: a stale `.env` fails at startup (`extra="forbid"`), which
  is louder than silently granting a different scope set. `scripts/hash_api_key.py`
  hashes (or `--generate`s) a token.
- **Task ownership.** `tasks.principal_id` (`String(255)`, non-null, server default
  `''`). Chosen over nullable + backfill: legacy rows get `''`, which no
  authenticated principal can hold (the subject must be non-empty), so they are
  unreachable through the API without a backfill, and they are TTL-purged
  anyway. `TaskService.submit(principal_id=...)` is required; the API passes
  `principal.id`. `TaskStore.get(task_id, *, principal_id=None)` filters by owner
  in every adapter (memory, redis, postgres); `None` is the worker's
  owner-agnostic read. `TaskService.require_owned` backs the API and raises
  `task_not_found` (404) for another principal's task, identical to a missing one.
  The Postgres task+outbox insert persists the owner via `new_task_row`.
  No index: there is no list endpoint (add `(principal_id, created_at)` with one).
- Migration `0008_task_principal_id` (down_revision
  `0007_idempotency_claim_token`).

## Capabilities

### Modified Capabilities

- `platform/identity`: API-key authentication, per-client principal.
- `messaging/tasks-ownership`: tasks are readable only by their submitter.

## Impact

- Deployers: replace `AUTH_BEARER_TOKEN`/`AUTH_SUBJECT`/`AUTH_ROLES` with
  `AUTH_API_KEYS` (`subject:scopes:sha256hex`) before upgrading; run
  `alembic upgrade head`; tasks submitted before the upgrade can no longer be
  polled through the API (clients should resubmit). Rate-limit buckets are now
  per subject. Scopes are no longer implicitly `admin`.
- Code: `app/modules/platform/identity/**`, `app/core/config/{platform,runtime,__init__}.py`,
  `app/modules/messaging/tasks/**`, `app/api/v1/completions/tasks.py`,
  `alembic/versions/0008_*`, `scripts/hash_api_key.py`, docs and tests.
- Callers of `TaskService.submit` must pass `principal_id`.
