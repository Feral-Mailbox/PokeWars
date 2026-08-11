"""add match-start coordinates on game units

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-08-11 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_units", sa.Column("match_start_x", sa.Integer(), nullable=True))
    op.add_column("game_units", sa.Column("match_start_y", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE game_units SET match_start_x = starting_x, match_start_y = starting_y "
        "WHERE match_start_x IS NULL OR match_start_y IS NULL"
    )


def downgrade() -> None:
    op.drop_column("game_units", "match_start_y")
    op.drop_column("game_units", "match_start_x")
