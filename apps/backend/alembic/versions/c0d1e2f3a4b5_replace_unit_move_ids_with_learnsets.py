"""replace unit move_ids with learnsets

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-06-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("units", sa.Column("level_up_moves", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("units", sa.Column("tm_moves", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("units", sa.Column("egg_moves", sa.JSON(), nullable=False, server_default="[]"))
    op.drop_column("units", "move_ids")


def downgrade() -> None:
    op.add_column("units", sa.Column("move_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.drop_column("units", "egg_moves")
    op.drop_column("units", "tm_moves")
    op.drop_column("units", "level_up_moves")
