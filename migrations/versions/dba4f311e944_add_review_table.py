"""add review table

Revision ID: dba4f311e944
Revises: 11d1f79aef4d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "dba4f311e944"
down_revision: str | None = "11d1f79aef4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.String(length=2000), nullable=False),
        sa.Column("user_uid", sa.Uuid(), nullable=False),
        sa.Column("book_uid", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("update_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),
        sa.ForeignKeyConstraint(["book_uid"], ["books.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_uid"], ["users.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid"),
    )


def downgrade() -> None:
    op.drop_table("reviews")
