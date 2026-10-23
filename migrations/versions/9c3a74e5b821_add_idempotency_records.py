"""add idempotency records

Revision ID: 9c3a74e5b821
Revises: 6f47c8e912ab
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c3a74e5b821"
down_revision: str | None = "6f47c8e912ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("user_uid", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_uid"], ["users.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid"),
        sa.UniqueConstraint(
            "user_uid",
            "operation",
            "key",
            name="uq_idempotency_records_user_operation_key",
        ),
    )
    op.create_index(
        "ix_idempotency_records_user_uid",
        "idempotency_records",
        ["user_uid"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_idempotency_records_user_uid",
        table_name="idempotency_records",
    )
    op.drop_table("idempotency_records")
