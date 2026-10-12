"""add idempotency_keys.claim_token (completion fence) and expires_at index (purge)

Revision ID: 0007_idempotency_claim_token
Revises: 0006_drop_quota_resv_idx
Create Date: 2026-10-12 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_idempotency_claim_token"
down_revision: str | Sequence[str] | None = "0006_drop_quota_resv_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: rows claimed before this revision keep NULL and can only expire
    # or be reclaimed (never completed), which is the safe outcome.
    op.add_column(
        "idempotency_keys", sa.Column("claim_token", sa.String(length=36), nullable=True)
    )
    op.create_index(
        "ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_column("idempotency_keys", "claim_token")
