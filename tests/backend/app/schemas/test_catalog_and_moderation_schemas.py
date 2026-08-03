from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.abilities import AbilitySchema
from app.schemas.items import ItemSchema
from app.schemas.moderation import (
    AdminBanRequest,
    InfractionDetail,
    InfractionSummary,
    MuteRequest,
    RoleChangeRequest,
    StaffActionRecord,
    StaffMember,
    TempBanRequest,
    UserModerationSummary,
)
from app.schemas.moves import MoveSchema


def test_item_schema_round_trip():
    item = ItemSchema(
        id=1,
        name="Oran Berry",
        slug="oran_berry",
        category="berry",
        cost=100,
        description="Restores HP",
        effects=["heal:10"],
        natural_gift_type="Normal",
        natural_gift_power=60,
        flavor="sweet",
        boost_type=None,
        move_id=None,
    )
    assert item.slug == "oran_berry"
    assert item.effects == ["heal:10"]


def test_move_schema_round_trip():
    move = MoveSchema(
        id=1,
        name="Tackle",
        description="A full-body charge",
        type="Normal",
        category="Physical",
        power=40,
        accuracy=100,
        pp=35,
        makes_contact=True,
        affected_by_protect=True,
        affected_by_magic_coat=False,
        affected_by_snatch=False,
        affected_by_mirror_move=True,
        affected_by_kings_rock=True,
        move_trait=0,
        range="adjacent",
        targeting="single",
        cooldown=0,
        effects=[],
    )
    assert move.power == 40
    assert move.effects == []


def test_ability_schema_round_trip():
    ability = AbilitySchema(
        id=1,
        name="Levitate",
        slug="levitate",
        description="Ground immunity",
        generation=3,
        effect=["immune:ground"],
    )
    assert ability.generation == 3
    assert ability.effect == ["immune:ground"]


def test_moderation_summary_and_detail():
    now = datetime.now(timezone.utc)
    summary = InfractionSummary(
        id=1,
        user_id=2,
        username="ash",
        game_id=3,
        game_link="abc",
        censored_message="***",
        severity="high",
        status="pending",
        created_at=now,
        matched_term_count=1,
    )
    detail = InfractionDetail(
        **summary.model_dump(),
        original_message="bad word",
        matched_terms=["bad"],
    )
    assert detail.original_message == "bad word"
    assert detail.matched_terms == ["bad"]


def test_user_moderation_and_staff_models():
    user = UserModerationSummary(
        id=1,
        username="ash",
        role="user",
        is_banned=False,
        pending_infractions=0,
        total_infractions=1,
        is_muted=False,
    )
    staff = StaffMember(id=2, username="mod", role="moderator")
    record = StaffActionRecord(
        id=1,
        actor_id=2,
        actor_username="mod",
        target_user_id=1,
        target_username="ash",
        action_type="mute",
        created_at=datetime.now(timezone.utc),
    )
    assert user.is_muted is False
    assert staff.role == "moderator"
    assert record.action_type == "mute"


def test_moderation_action_request_bounds():
    mute = MuteRequest(reason="spam", hours=24)
    assert mute.hours == 24
    with pytest.raises(ValidationError):
        MuteRequest(reason="spam", hours=100)

    ban = TempBanRequest(reason="abuse", days=3)
    assert ban.days == 3
    with pytest.raises(ValidationError):
        TempBanRequest(reason="abuse", days=30)

    admin_ban = AdminBanRequest(reason="cheat", permanent=True)
    assert admin_ban.permanent is True

    role = RoleChangeRequest(role="moderator")
    assert role.role == "moderator"
    with pytest.raises(ValidationError):
        RoleChangeRequest(role="superadmin")
