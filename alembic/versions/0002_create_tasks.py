"""create tasks table

Revision ID: 0002_create_tasks
Revises: 0001_create_foundation_tables
Create Date: 2026-05-21 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_create_tasks"
down_revision: str | Sequence[str] | None = "0001_create_foundation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_type", "tasks", ["type"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_status_created_at", "tasks", ["status", "created_at"])
    op.create_index("ix_tasks_expires_at", "tasks", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_expires_at", table_name="tasks")
    op.drop_index("ix_tasks_status_created_at", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_type", table_name="tasks")
    op.drop_table("tasks")
