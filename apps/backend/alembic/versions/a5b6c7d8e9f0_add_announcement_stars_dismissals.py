"""add announcement stars and dismissals

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-27 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_announcement_stars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "announcement_id",
            sa.Integer(),
            sa.ForeignKey("staff_announcements.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "announcement_id",
            name="uq_staff_announcement_stars_user_announcement",
        ),
    )
    op.create_index(
        "ix_staff_announcement_stars_user_id",
        "staff_announcement_stars",
        ["user_id"],
    )
    op.create_index(
        "ix_staff_announcement_stars_announcement_id",
        "staff_announcement_stars",
        ["announcement_id"],
    )

    op.create_table(
        "staff_announcement_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "announcement_id",
            sa.Integer(),
            sa.ForeignKey("staff_announcements.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "announcement_id",
            name="uq_staff_announcement_dismissals_user_announcement",
        ),
    )
    op.create_index(
        "ix_staff_announcement_dismissals_user_id",
        "staff_announcement_dismissals",
        ["user_id"],
    )
    op.create_index(
        "ix_staff_announcement_dismissals_announcement_id",
        "staff_announcement_dismissals",
        ["announcement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staff_announcement_dismissals_announcement_id",
        table_name="staff_announcement_dismissals",
    )
    op.drop_index(
        "ix_staff_announcement_dismissals_user_id",
        table_name="staff_announcement_dismissals",
    )
    op.drop_table("staff_announcement_dismissals")
    op.drop_index(
        "ix_staff_announcement_stars_announcement_id",
        table_name="staff_announcement_stars",
    )
    op.drop_index(
        "ix_staff_announcement_stars_user_id",
        table_name="staff_announcement_stars",
    )
    op.drop_table("staff_announcement_stars")
