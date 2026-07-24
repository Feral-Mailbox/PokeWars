"""add unique trainer_id to users

Revision ID: a9b0c1d2e3f4
Revises: e7f8a9b0c1d2
Create Date: 2026-07-24 15:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import secrets


revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("trainer_id", sa.String(length=8), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM users")).fetchall()
    used: set[str] = set()
    for (user_id,) in rows:
        while True:
            candidate = f"{secrets.randbits(32):08X}"
            if candidate not in used:
                used.add(candidate)
                break
        conn.execute(
            sa.text("UPDATE users SET trainer_id = :tid WHERE id = :uid"),
            {"tid": candidate, "uid": user_id},
        )

    op.alter_column("users", "trainer_id", existing_type=sa.String(length=8), nullable=False)
    op.create_index(op.f("ix_users_trainer_id"), "users", ["trainer_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_trainer_id"), table_name="users")
    op.drop_column("users", "trainer_id")
