from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import StaffAction, StaffActionType, User, UserRole


def log_staff_action(
    db: Session,
    *,
    actor_id: int,
    action_type: StaffActionType,
    target_user_id: int | None = None,
    infraction_id: int | None = None,
    reason: str | None = None,
    action_metadata: dict | None = None,
) -> StaffAction:
    record = StaffAction(
        actor_id=actor_id,
        target_user_id=target_user_id,
        infraction_id=infraction_id,
        action_type=action_type,
        reason=reason,
        action_metadata=action_metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    return record


def apply_ban(
    db: Session,
    *,
    actor: User,
    target: User,
    reason: str,
    expires_at: datetime | None,
    action_type: StaffActionType,
    infraction_id: int | None = None,
) -> None:
    if target.role in (UserRole.moderator, UserRole.admin):
        raise HTTPException(status_code=403, detail="Cannot restrict staff accounts.")
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="You cannot restrict your own account.")

    now = datetime.now(timezone.utc)
    target.is_banned = True
    target.banned_at = now
    target.banned_by = actor.id
    target.ban_reason = reason
    target.ban_expires_at = expires_at
    db.add(target)
    log_staff_action(
        db,
        actor_id=actor.id,
        target_user_id=target.id,
        infraction_id=infraction_id,
        action_type=action_type,
        reason=reason,
        action_metadata={"expires_at": expires_at.isoformat() if expires_at else None},
    )
