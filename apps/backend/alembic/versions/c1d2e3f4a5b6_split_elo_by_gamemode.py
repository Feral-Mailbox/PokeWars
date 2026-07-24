"""split user elo into per-gamemode ratings

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-07-24 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("elo_conquest", sa.Integer(), nullable=False, server_default="1000"),
    )
    op.add_column(
        "users",
        sa.Column("elo_war", sa.Integer(), nullable=False, server_default="1000"),
    )

    # Carry over the legacy single elo into both ladders when present.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "elo" in columns:
        conn.execute(
            sa.text(
                "UPDATE users SET elo_conquest = COALESCE(elo, 1000), "
                "elo_war = COALESCE(elo, 1000)"
            )
        )
        op.drop_column("users", "elo")

    op.alter_column("users", "elo_conquest", server_default=None)
    op.alter_column("users", "elo_war", server_default=None)


def downgrade() -> None:
    op.add_column("users", sa.Column("elo", sa.Integer(), nullable=True))
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE users SET elo = COALESCE(elo_conquest, elo_war, 1000)")
    )
    op.drop_column("users", "elo_war")
    op.drop_column("users", "elo_conquest")
