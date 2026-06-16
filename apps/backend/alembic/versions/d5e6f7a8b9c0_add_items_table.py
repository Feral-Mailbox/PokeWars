"""add items table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("effects", sa.JSON(), nullable=True),
        sa.Column("natural_gift_type", sa.String(), nullable=True),
        sa.Column("natural_gift_power", sa.Integer(), nullable=True),
        sa.Column("flavor", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_items_slug"), "items", ["slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_items_slug"), table_name="items")
    op.drop_table("items")
