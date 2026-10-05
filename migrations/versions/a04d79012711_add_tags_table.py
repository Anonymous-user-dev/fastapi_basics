"""add tags table

Revision ID: a04d79012711
Revises: dba4f311e944
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a04d79012711"
down_revision: str | None = "dba4f311e944"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("uid"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_tags_name", "tags", ["name"])
    op.create_table(
        "book_tags",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("book_id", "tag_id"),
    )


def downgrade() -> None:
    op.drop_table("book_tags")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
