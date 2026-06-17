"""create foundation schema marker

Revision ID: 0001_create_foundation_tables
Revises:
Create Date: 2026-05-20 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_create_foundation_tables"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("langfuse_trace_id", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("pii_scrubbed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_actor_id",
        "audit_events",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_event_type",
        "audit_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_request_id",
        "audit_events",
        ["request_id"],
        unique=False,
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("principal_id", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_id",
            "key",
            name="uq_idempotency_keys_principal_key",
        ),
    )
    op.create_index(
        "ix_idempotency_keys_principal_id",
        "idempotency_keys",
        ["principal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_principal_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_table("audit_events")
