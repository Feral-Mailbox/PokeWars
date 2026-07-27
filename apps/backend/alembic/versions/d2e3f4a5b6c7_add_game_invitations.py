"""add game_invitations table

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-27 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INVITATION_STATUS = postgresql.ENUM(
    "pending",
    "accepted",
    "declined",
    "cancelled",
    "expired",
    name="invitationstatus",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE invitationstatus AS ENUM (
                'pending', 'accepted', 'declined', 'cancelled', 'expired'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "game_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("inviter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invitee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "status",
            INVITATION_STATUS,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_game_invitations_game_id", "game_invitations", ["game_id"])
    op.create_index("ix_game_invitations_inviter_id", "game_invitations", ["inviter_id"])
    op.create_index("ix_game_invitations_invitee_id", "game_invitations", ["invitee_id"])
    op.create_index("ix_game_invitations_status", "game_invitations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_game_invitations_status", table_name="game_invitations")
    op.drop_index("ix_game_invitations_invitee_id", table_name="game_invitations")
    op.drop_index("ix_game_invitations_inviter_id", table_name="game_invitations")
    op.drop_index("ix_game_invitations_game_id", table_name="game_invitations")
    op.drop_table("game_invitations")
    op.execute("DROP TYPE IF EXISTS invitationstatus")
