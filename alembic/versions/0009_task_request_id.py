"""add tasks.request_id (submitting request id, re-announced on reclaim)

Revision ID: 0009_task_request_id
Revises: 0008_task_principal_id
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_task_request_id"
down_revision: str | Sequence[str] | None = "0008_task_principal_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no backfill: tasks that predate this are reclaimed untraced.
    op.add_column(
        "tasks", sa.Column("request_id", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tasks", "request_id")
