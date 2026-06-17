"""Persistent task store for **asynchronous** endpoints.

Use this module for endpoints that return ``202 + task_id`` and run the work
in a background worker. The store's primary key is the source of truth for
deduplication — there is no separate idempotency cache layer.

To dedupe across client retries, derive a deterministic ``task_id`` from the
client-provided idempotency hint, e.g.::

    task_id = hashlib.sha256(f"{principal.id}:{idempotency_key}".encode()).hexdigest()[
        :32
    ]

The unique constraint on ``task_id`` makes resubmission a no-op (the store
returns the existing row instead of inserting a duplicate).

Do not also use ``app.modules.platform.idempotency`` for the same endpoint —
combining the two causes stuck-in-progress records and TTL drift. See that
module's docstring for the conflict rationale.
"""

from app.modules.messaging.tasks.models import Task, TaskStatus
from app.modules.messaging.tasks.store import TaskStore

__all__ = ["Task", "TaskStatus", "TaskStore"]
