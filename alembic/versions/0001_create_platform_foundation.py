"""create foundation tables

Revision ID: 0001_create_foundation_tables
Revises:
Create Date: 2026-05-20 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_foundation_tables"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("rating", sa.String(length=32), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("comment", sa.String(length=2000), nullable=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("api_key_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_request_id", "feedback", ["request_id"])
    op.create_index("ix_feedback_trace_id", "feedback", ["trace_id"])
    op.create_index("ix_feedback_target_id", "feedback", ["target_id"])
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_index("ix_feedback_api_key_id", "feedback", ["api_key_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_api_key_id", table_name="feedback")
    op.drop_index("ix_feedback_user_id", table_name="feedback")
    op.drop_index("ix_feedback_target_id", table_name="feedback")
    op.drop_index("ix_feedback_trace_id", table_name="feedback")
    op.drop_index("ix_feedback_request_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_table("api_keys")
