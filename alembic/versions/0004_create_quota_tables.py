"""create quota tables

Revision ID: 0004_create_quota_tables
Revises: 0003_create_outbox_events
Create Date: 2026-06-03 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_create_quota_tables"
down_revision: str | Sequence[str] | None = "0003_create_outbox_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quota_counters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("window_key", sa.String(length=64), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("quota_limit", sa.Integer(), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_id",
            "resource",
            "window_key",
            name="uq_quota_counters_subject_resource_window",
        ),
    )
    op.create_index("ix_quota_counters_subject_id", "quota_counters", ["subject_id"])
    op.create_index("ix_quota_counters_resource", "quota_counters", ["resource"])

    op.create_table(
        "quota_reservations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("window_key", sa.String(length=64), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_id",
            "resource",
            "window_key",
            "idempotency_key",
            name="uq_quota_reservations_idempotency",
        ),
    )
    op.create_index(
        "ix_quota_reservations_subject_id",
        "quota_reservations",
        ["subject_id"],
    )
    op.create_index(
        "ix_quota_reservations_resource",
        "quota_reservations",
        ["resource"],
    )
    op.create_index(
        "ix_quota_reservations_status",
        "quota_reservations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_quota_reservations_status", table_name="quota_reservations")
    op.drop_index("ix_quota_reservations_resource", table_name="quota_reservations")
    op.drop_index("ix_quota_reservations_subject_id", table_name="quota_reservations")
    op.drop_table("quota_reservations")
    op.drop_index("ix_quota_counters_resource", table_name="quota_counters")
    op.drop_index("ix_quota_counters_subject_id", table_name="quota_counters")
    op.drop_table("quota_counters")
