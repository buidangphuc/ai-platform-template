"""add tasks.principal_id (owner of the task; API reads are scoped to it)

Revision ID: 0008_task_principal_id
Revises: 0007_idempotency_claim_token
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_task_principal_id"
down_revision: str | Sequence[str] | None = "0007_idempotency_claim_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # '' for rows that predate ownership: no authenticated principal has an empty
    # subject, so the API never serves them (they expire by TTL). No backfill.
    op.add_column(
        "tasks",
        sa.Column(
            "principal_id", sa.String(length=255), nullable=False, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "principal_id")
