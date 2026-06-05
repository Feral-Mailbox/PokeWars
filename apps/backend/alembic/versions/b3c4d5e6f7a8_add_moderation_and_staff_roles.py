"""add moderation and staff roles

Revision ID: b3c4d5e6f7a8
Revises: f2e3d4c5b6a7
Create Date: 2026-06-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "f2e3d4c5b6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = postgresql.ENUM("user", "moderator", "admin", name="userrole", create_type=False)
infraction_status = postgresql.ENUM(
    "pending_review",
    "reviewed",
    "dismissed",
    "action_taken",
    name="infractionstatus",
    create_type=False,
)
infraction_severity = postgresql.ENUM("slur", name="infractionseverity", create_type=False)
staff_action_type = postgresql.ENUM(
    "dismiss",
    "warn",
    "mute",
    "temp_ban",
    "perm_ban",
    "unban",
    "promote_moderator",
    "demote_moderator",
    "promote_admin",
    "demote_admin",
    name="staffactiontype",
    create_type=False,
)
restriction_type = postgresql.ENUM("mute", name="restrictiontype", create_type=False)


def _create_enums() -> None:
    bind = op.get_bind()
    for enum_type in (
        user_role,
        infraction_status,
        infraction_severity,
        staff_action_type,
        restriction_type,
    ):
        enum_type.create(bind, checkfirst=True)


def upgrade() -> None:
    _create_enums()

    op.add_column(
        "users",
        sa.Column("role", user_role, nullable=False, server_default="user"),
    )
    op.add_column("users", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("banned_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("ban_reason", sa.String(), nullable=True))
    op.add_column("users", sa.Column("ban_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_users_banned_by", "users", "users", ["banned_by"], ["id"])

    op.create_table(
        "chat_infractions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("original_message", sa.String(), nullable=False),
        sa.Column("censored_message", sa.String(), nullable=False),
        sa.Column("matched_terms", sa.JSON(), nullable=False),
        sa.Column("severity", infraction_severity, nullable=False, server_default="slur"),
        sa.Column("status", infraction_status, nullable=False, server_default="pending_review"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderator_notes", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_infractions_user_id", "chat_infractions", ["user_id"])
    op.create_index("ix_chat_infractions_game_id", "chat_infractions", ["game_id"])

    op.create_table(
        "staff_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("infraction_id", sa.Integer(), nullable=True),
        sa.Column("action_type", staff_action_type, nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("action_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["infraction_id"], ["chat_infractions.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_staff_actions_actor_id", "staff_actions", ["actor_id"])
    op.create_index("ix_staff_actions_target_user_id", "staff_actions", ["target_user_id"])

    op.create_table(
        "user_restrictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("restriction_type", restriction_type, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_restrictions_user_id", "user_restrictions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_restrictions_user_id", table_name="user_restrictions")
    op.drop_table("user_restrictions")
    op.drop_index("ix_staff_actions_target_user_id", table_name="staff_actions")
    op.drop_index("ix_staff_actions_actor_id", table_name="staff_actions")
    op.drop_table("staff_actions")
    op.drop_index("ix_chat_infractions_game_id", table_name="chat_infractions")
    op.drop_index("ix_chat_infractions_user_id", table_name="chat_infractions")
    op.drop_table("chat_infractions")
    op.drop_constraint("fk_users_banned_by", "users", type_="foreignkey")
    op.drop_column("users", "ban_expires_at")
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "banned_by")
    op.drop_column("users", "banned_at")
    op.drop_column("users", "is_banned")
    op.drop_column("users", "role")

    bind = op.get_bind()
    for enum_type in (
        restriction_type,
        staff_action_type,
        infraction_severity,
        infraction_status,
        user_role,
    ):
        enum_type.drop(bind, checkfirst=True)
