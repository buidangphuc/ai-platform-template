"""align schema with models: drop redundant indexes, add checks and partial index

Revision ID: 0005_schema_drift_cleanup
Revises: 0004_create_quota_tables
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_schema_drift_cleanup"
down_revision: str | Sequence[str] | None = "0004_create_quota_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Leftmost-prefix duplicates of composite/unique indexes.
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_outbox_events_status", table_name="outbox_events")
    op.drop_index("ix_idempotency_keys_principal_id", table_name="idempotency_keys")
    op.drop_index("ix_quota_counters_subject_id", table_name="quota_counters")

    op.create_index(
        "ix_tasks_processing_locked_until",
        "tasks",
        ["locked_until"],
        postgresql_where=sa.text("status = 'processing'"),
    )

    op.create_check_constraint(
        "ck_tasks_status",
        "tasks",
        "status IN ('queued', 'processing', 'completed', 'failed')",
    )
    op.create_check_constraint(
        "ck_outbox_events_status",
        "outbox_events",
        "status IN ('pending', 'published', 'failed')",
    )
    op.create_check_constraint(
        "ck_idempotency_keys_status",
        "idempotency_keys",
        "status IN ('in_progress', 'completed')",
    )
    op.create_check_constraint(
        "ck_quota_reservations_status",
        "quota_reservations",
        "status IN ('reserved', 'finalized', 'refunded')",
    )
    op.create_check_constraint(
        "ck_quota_counters_used_non_negative",
        "quota_counters",
        "used >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_quota_counters_used_non_negative", "quota_counters")
    op.drop_constraint("ck_quota_reservations_status", "quota_reservations")
    op.drop_constraint("ck_idempotency_keys_status", "idempotency_keys")
    op.drop_constraint("ck_outbox_events_status", "outbox_events")
    op.drop_constraint("ck_tasks_status", "tasks")

    op.drop_index("ix_tasks_processing_locked_until", table_name="tasks")

    op.create_index("ix_quota_counters_subject_id", "quota_counters", ["subject_id"])
    op.create_index(
        "ix_idempotency_keys_principal_id", "idempotency_keys", ["principal_id"]
    )
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
