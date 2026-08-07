"""add flag_tiles and unlock_tiles for Capture The Flag

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_map_states",
        sa.Column("flag_tiles", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "game_map_states",
        sa.Column("unlock_tiles", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("game_map_states", "unlock_tiles")
    op.drop_column("game_map_states", "flag_tiles")
