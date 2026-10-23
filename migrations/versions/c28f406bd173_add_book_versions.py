"""add book versions

Revision ID: c28f406bd173
Revises: 9c3a74e5b821
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c28f406bd173"
down_revision: str | None = "9c3a74e5b821"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "books",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("books", "version")
