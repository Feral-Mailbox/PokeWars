from datetime import datetime, timezone

from fastapi import Depends, Cookie, HTTPException
from sqlalchemy.orm import Session

from app.db.models import User, UserRole, UserRestriction, RestrictionType
from app.db.database import get_db as _get_db

MOD_MUTE_MAX_HOURS = 72
MOD_TEMP_BAN_MAX_DAYS = 7


def get_db():
    yield from _get_db()


def clear_expired_ban(user: User, db: Session) -> None:
    if not user.is_banned:
        return
    if user.ban_expires_at is None:
        return
    if user.ban_expires_at <= datetime.now(timezone.utc):
        user.is_banned = False
        user.banned_at = None
        user.banned_by = None
        user.ban_reason = None
        user.ban_expires_at = None
        db.add(user)
        db.commit()
        db.refresh(user)


def ban_is_active(user: User) -> bool:
    if not user.is_banned:
        return False
    if user.ban_expires_at is None:
        return True
    return user.ban_expires_at > datetime.now(timezone.utc)


def ensure_user_not_banned(user: User) -> None:
    if ban_is_active(user):
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Account restricted",
                "reason": user.ban_reason or "Your account has been restricted.",
                "expires_at": user.ban_expires_at.isoformat() if user.ban_expires_at else None,
            },
        )


def get_current_user(session_user: str = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    if session_user is None:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = db.query(User).filter(User.id == int(session_user)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    clear_expired_ban(user, db)
    ensure_user_not_banned(user)
    return user


def require_moderator(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.moderator, UserRole.admin):
        raise HTTPException(status_code=403, detail="Moderator access required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def user_is_muted(user_id: int, db: Session) -> bool:
    now = datetime.now(timezone.utc)
    active_mute = (
        db.query(UserRestriction)
        .filter(
            UserRestriction.user_id == user_id,
            UserRestriction.restriction_type == RestrictionType.mute,
            UserRestriction.revoked_at.is_(None),
            UserRestriction.expires_at > now,
        )
        .first()
    )
    return active_mute is not None


def ensure_user_can_chat(user: User, db: Session) -> None:
    ensure_user_not_banned(user)
    if user_is_muted(user.id, db):
        raise HTTPException(status_code=403, detail="You are muted and cannot send chat messages.")
