"""add comment moderation status

Revision ID: d54d29f3b0a1
Revises: b7fb5b66bab3
Create Date: 2026-03-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d54d29f3b0a1"
down_revision: Union[str, None] = "b7fb5b66bab3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "comments",
        sa.Column("moderation_status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE comments
            SET moderation_status = CASE
                WHEN is_approved IS TRUE THEN 'approved'
                ELSE 'hidden'
            END
            """
        )
    )
    op.alter_column("comments", "moderation_status", existing_type=sa.String(length=20), nullable=False)
    op.alter_column(
        "comments",
        "is_approved",
        existing_type=sa.Boolean(),
        existing_server_default=sa.text("true"),
        server_default=sa.text("false"),
        nullable=False,
    )
    op.create_index(op.f("ix_comments_moderation_status"), "comments", ["moderation_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_comments_moderation_status"), table_name="comments")
    op.alter_column(
        "comments",
        "is_approved",
        existing_type=sa.Boolean(),
        existing_server_default=sa.text("false"),
        server_default=sa.text("true"),
        nullable=False,
    )
    op.drop_column("comments", "moderation_status")
