"""add expires_at to game_invitations

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-27 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_invitations",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_game_invitations_expires_at", "game_invitations", ["expires_at"])
    # Backfill existing pending invites to expire 3 minutes after creation.
    op.execute(
        """
        UPDATE game_invitations
        SET expires_at = created_at + interval '3 minutes'
        WHERE expires_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_game_invitations_expires_at", table_name="game_invitations")
    op.drop_column("game_invitations", "expires_at")
