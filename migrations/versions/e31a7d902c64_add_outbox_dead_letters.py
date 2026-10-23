"""add outbox dead letters

Revision ID: e31a7d902c64
Revises: c28f406bd173
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e31a7d902c64"
down_revision: str | None = "c28f406bd173"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbox_events") as batch_op:
        batch_op.drop_constraint("ck_outbox_events_status", type_="check")
        batch_op.create_check_constraint(
            "ck_outbox_events_status",
            "status IN ('pending', 'processing', 'processed', 'failed')",
        )


def downgrade() -> None:
    op.execute("UPDATE outbox_events SET status = 'pending' WHERE status = 'failed'")
    with op.batch_alter_table("outbox_events") as batch_op:
        batch_op.drop_constraint("ck_outbox_events_status", type_="check")
        batch_op.create_check_constraint(
            "ck_outbox_events_status",
            "status IN ('pending', 'processing', 'processed')",
        )
