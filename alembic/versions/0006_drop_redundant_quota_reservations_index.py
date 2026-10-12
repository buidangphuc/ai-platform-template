"""drop ix_quota_reservations_subject_id (leftmost prefix of the idempotency unique)

Revision ID: 0006_drop_quota_resv_idx
Revises: 0005_schema_drift_cleanup
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence

from alembic import op

revision: str = "0006_drop_quota_resv_idx"
down_revision: str | Sequence[str] | None = "0005_schema_drift_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # uq_quota_reservations_idempotency is (subject_id, resource, window_key,
    # idempotency_key): any lookup by subject_id alone already uses it.
    op.drop_index("ix_quota_reservations_subject_id", table_name="quota_reservations")


def downgrade() -> None:
    op.create_index(
        "ix_quota_reservations_subject_id", "quota_reservations", ["subject_id"]
    )
