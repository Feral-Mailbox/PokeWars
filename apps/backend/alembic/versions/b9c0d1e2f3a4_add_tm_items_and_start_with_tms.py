"""add tm item move_id and game start_with_tms

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-06-16 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("move_id", sa.Integer(), nullable=True))
    op.add_column(
        "games",
        sa.Column("start_with_tms", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("games", "start_with_tms", server_default=None)


def downgrade() -> None:
    op.drop_column("games", "start_with_tms")
    op.drop_column("items", "move_id")
