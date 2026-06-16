"""add ability generation and slug

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("abilities_name_key", "abilities", type_="unique")
    op.add_column("abilities", sa.Column("slug", sa.String(), nullable=True))
    op.add_column("abilities", sa.Column("generation", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE abilities
        SET slug = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '_', 'g')),
            generation = 3
        WHERE slug IS NULL
        """
    )
    op.alter_column("abilities", "slug", nullable=False)
    op.alter_column("abilities", "generation", nullable=False)
    op.create_index(op.f("ix_abilities_slug"), "abilities", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_abilities_slug"), table_name="abilities")
    op.drop_column("abilities", "generation")
    op.drop_column("abilities", "slug")
    op.create_unique_constraint("abilities_name_key", "abilities", ["name"])
