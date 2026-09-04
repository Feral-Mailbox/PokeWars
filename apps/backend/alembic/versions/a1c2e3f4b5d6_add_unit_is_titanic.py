"""add is_titanic and titanic_footprint to units

Revision ID: a1c2e3f4b5d6
Revises: f0a1b2c3d4e5
Create Date: 2026-09-04 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c2e3f4b5d6"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "units",
        sa.Column("is_titanic", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "units",
        sa.Column("titanic_footprint", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("units", "titanic_footprint")
    op.drop_column("units", "is_titanic")
