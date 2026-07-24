from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import app.db.models as models
from app.db.models import RestrictionType, UserRole
from app.dependencies import (
    _as_utc,
    ban_is_active,
    clear_expired_ban,
    ensure_user_can_chat,
    ensure_user_not_banned,
    get_current_user,
    get_db,
    require_admin,
    require_moderator,
    user_is_muted,
)
from app.routes.auth import hash_password
from app.utils.session import create_session_token


def _user(db, username="depuser", **kwargs):
    defaults = dict(
        username=username,
        email=f"{username}@example.com",
        hashed_password=hash_password("pw"),
        role=UserRole.user,
    )
    defaults.update(kwargs)
    user = models.User(**defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_get_db_delegates(db):
    gen = get_db()
    session = next(gen)
    assert session is not None
    with pytest.raises(StopIteration):
        next(gen)


def test_as_utc_branches():
    assert _as_utc(None) is None
    naive = datetime(2024, 1, 1, 12, 0, 0)
    aware = _as_utc(naive)
    assert aware.tzinfo == timezone.utc
    already = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert _as_utc(already).tzinfo == timezone.utc
    offset = timezone(timedelta(hours=-5))
    converted = _as_utc(datetime(2024, 1, 1, 12, 0, 0, tzinfo=offset))
    assert converted.tzinfo == timezone.utc


def test_clear_expired_ban_early_returns(db):
    user = _user(db, "clear1")
    clear_expired_ban(user, db)  # not banned

    user.is_banned = True
    user.ban_expires_at = None
    db.commit()
    clear_expired_ban(user, db)  # permanent
    db.refresh(user)
    assert user.is_banned is True


def test_clear_expired_ban_clears_elapsed_ban(db):
    user = _user(
        db,
        "expiredban",
        is_banned=True,
        ban_reason="old",
        ban_expires_at=datetime.utcnow() - timedelta(days=1),
    )
    clear_expired_ban(user, db)
    db.refresh(user)
    assert user.is_banned is False
    assert user.ban_expires_at is None


def test_ban_is_active_permanent_and_temporary(db):
    user = _user(db, "ban1", is_banned=False)
    assert ban_is_active(user) is False

    user.is_banned = True
    user.ban_expires_at = None
    assert ban_is_active(user) is True

    user.ban_expires_at = datetime.utcnow() + timedelta(days=1)
    assert ban_is_active(user) is True

    user.ban_expires_at = datetime.utcnow() - timedelta(days=1)
    assert ban_is_active(user) is False


def test_ensure_user_not_banned_raises(db):
    user = _user(db, "ban2", is_banned=True, ban_reason=None, ban_expires_at=None)
    with pytest.raises(HTTPException) as exc:
        ensure_user_not_banned(user)
    assert exc.value.status_code == 403
    assert "restricted" in exc.value.detail["reason"].lower() or "Account" in exc.value.detail["message"]


def test_get_current_user_paths(db):
    with pytest.raises(HTTPException) as exc:
        get_current_user(session_user=None, db=db)
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException):
        get_current_user(session_user="bad-token", db=db)

    with pytest.raises(HTTPException):
        get_current_user(session_user=create_session_token(99999), db=db)

    user = _user(db, "okuser")
    loaded = get_current_user(session_user=create_session_token(user.id), db=db)
    assert loaded.id == user.id

    banned = _user(db, "banneduser", is_banned=True, ban_expires_at=None, ban_reason="x")
    with pytest.raises(HTTPException) as banned_exc:
        get_current_user(session_user=create_session_token(banned.id), db=db)
    assert banned_exc.value.status_code == 403


def test_require_moderator_and_admin(db):
    user = _user(db, "plain")
    mod = _user(db, "moddy", role=UserRole.moderator)
    admin = _user(db, "addy", role=UserRole.admin)

    with pytest.raises(HTTPException):
        require_moderator(user=user)
    assert require_moderator(user=mod).id == mod.id
    assert require_moderator(user=admin).id == admin.id

    with pytest.raises(HTTPException):
        require_admin(user=mod)
    assert require_admin(user=admin).id == admin.id


def test_mute_and_chat_guards(db):
    user = _user(db, "chatter")
    assert user_is_muted(user.id, db) is False
    ensure_user_can_chat(user, db)

    mute = models.UserRestriction(
        user_id=user.id,
        restriction_type=RestrictionType.mute,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        created_by=user.id,
        reason="spam",
        created_at=datetime.now(timezone.utc),
    )
    db.add(mute)
    db.commit()
    assert user_is_muted(user.id, db) is True
    with pytest.raises(HTTPException) as exc:
        ensure_user_can_chat(user, db)
    assert exc.value.status_code == 403
