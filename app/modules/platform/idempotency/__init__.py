"""Idempotency for **synchronous** HTTP endpoints.

Use this module when the server produces the final response within the same
request (e.g. ``POST /payments`` returning the created record). The flow:

1. ``replay_or_start_idempotent_request`` — claim the key, replay if cached
2. handler runs business logic
3. ``store_idempotent_response`` — cache the final response

Do **not** combine this module with async task endpoints (``POST /tasks``
returning 202 + ``task_id``). The two patterns conflict:

- Stuck ``in_progress`` records resubmit the same task → duplicate worker run
- Cached 202 response does not reflect the live task state
- ``IDEMPOTENCY_TTL_SECONDS`` and ``TASK_TTL_SECONDS`` drift

For async endpoints, dedupe on a deterministic ``task_id`` instead and rely on
the unique constraint of ``app.modules.messaging.tasks``. See that module for
guidance.
"""
