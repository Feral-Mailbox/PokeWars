"""add staff_announcements table

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-27 13:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_announcements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("message", sa.String(length=4000), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_staff_announcements_author_id", "staff_announcements", ["author_id"])
    op.create_index("ix_staff_announcements_created_at", "staff_announcements", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_staff_announcements_created_at", table_name="staff_announcements")
    op.drop_index("ix_staff_announcements_author_id", table_name="staff_announcements")
    op.drop_table("staff_announcements")
