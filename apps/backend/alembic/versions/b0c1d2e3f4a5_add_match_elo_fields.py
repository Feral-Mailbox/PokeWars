"""add elimination_order and elo_applied to game_status

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-07-24 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_status", sa.Column("elimination_order", sa.JSON(), nullable=True))
    op.add_column(
        "game_status",
        sa.Column("elo_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("game_status", "elo_applied")
    op.drop_column("game_status", "elimination_order")
