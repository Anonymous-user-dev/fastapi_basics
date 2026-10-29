"""remove redundant unique indexes

Revision ID: f7b2c14d83aa
Revises: e31a7d902c64
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f7b2c14d83aa"
down_revision: str | None = "e31a7d902c64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_tags_name", table_name="tags")


def downgrade() -> None:
    op.create_index("ix_tags_name", "tags", ["name"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
