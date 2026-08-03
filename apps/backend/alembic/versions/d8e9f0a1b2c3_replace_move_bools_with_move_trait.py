"""Replace sound/wind/slicing booleans with move_trait integer

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-03 17:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("moves", sa.Column("move_trait", sa.Integer(), nullable=True))

    # Migrate legacy boolean flags → mutually exclusive move_trait ints.
    # Priority when multiple were set: sound > wind > slicing.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE moves SET move_trait = CASE
                WHEN sound_based IS TRUE THEN 1
                WHEN wind_based IS TRUE THEN 2
                WHEN slicing_based IS TRUE THEN 3
                ELSE 0
            END
            """
        )
    )

    op.drop_column("moves", "sound_based")
    op.drop_column("moves", "wind_based")
    op.drop_column("moves", "slicing_based")


def downgrade() -> None:
    op.add_column("moves", sa.Column("sound_based", sa.Boolean(), nullable=True))
    op.add_column("moves", sa.Column("wind_based", sa.Boolean(), nullable=True))
    op.add_column("moves", sa.Column("slicing_based", sa.Boolean(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE moves SET
                sound_based = CASE WHEN move_trait = 1 THEN TRUE ELSE FALSE END,
                wind_based = CASE WHEN move_trait = 2 THEN TRUE ELSE FALSE END,
                slicing_based = CASE WHEN move_trait = 3 THEN TRUE ELSE FALSE END
            """
        )
    )

    op.drop_column("moves", "move_trait")
