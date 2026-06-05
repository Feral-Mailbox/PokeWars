from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import StaffAction, StaffActionType, User, UserRole
from app.dependencies import get_db, require_admin
from app.moderation.staff_actions import apply_ban, log_staff_action
from app.schemas.moderation import AdminBanRequest, ModerationActionRequest, RoleChangeRequest, StaffActionRecord, StaffMember

router = APIRouter(prefix="/admin", tags=["admin"])


def _count_admins(db: Session) -> int:
    return db.query(User).filter(User.role == UserRole.admin).count()


@router.get("/staff", response_model=list[StaffMember])
def list_staff(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    staff = db.query(User).filter(User.role.in_([UserRole.moderator, UserRole.admin])).order_by(User.username).all()
    return [StaffMember(id=user.id, username=user.username, role=user.role.value) for user in staff]


@router.get("/audit-log", response_model=list[StaffActionRecord])
def get_audit_log(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    records = db.query(StaffAction).order_by(StaffAction.created_at.desc()).limit(200).all()
    output: list[StaffActionRecord] = []
    for record in records:
        actor = db.query(User).filter(User.id == record.actor_id).first()
        target = (
            db.query(User).filter(User.id == record.target_user_id).first()
            if record.target_user_id
            else None
        )
        output.append(
            StaffActionRecord(
                id=record.id,
                actor_id=record.actor_id,
                actor_username=actor.username if actor else "Unknown",
                target_user_id=record.target_user_id,
                target_username=target.username if target else None,
                infraction_id=record.infraction_id,
                action_type=record.action_type.value,
                reason=record.reason,
                action_metadata=record.action_metadata,
                created_at=record.created_at,
            )
        )
    return output


@router.post("/users/{user_id}/ban")
def ban_user(
    user_id: int,
    payload: AdminBanRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    expires_at = None
    if not payload.permanent:
        if payload.days is None:
            raise HTTPException(status_code=400, detail="Temporary bans require a day count.")
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.days)

    apply_ban(
        db,
        actor=admin,
        target=target,
        reason=payload.reason,
        expires_at=expires_at,
        action_type=StaffActionType.perm_ban if payload.permanent else StaffActionType.temp_ban,
    )
    db.commit()
    return {
        "ok": True,
        "permanent": payload.permanent,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.post("/users/{user_id}/unban")
def unban_user(
    user_id: int,
    payload: ModerationActionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.is_banned = False
    target.banned_at = None
    target.banned_by = None
    target.ban_reason = None
    target.ban_expires_at = None
    db.add(target)
    log_staff_action(
        db,
        actor_id=admin.id,
        target_user_id=target.id,
        action_type=StaffActionType.unban,
        reason=payload.reason,
    )
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/role")
def change_user_role(
    user_id: int,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and payload.role != UserRole.admin.value:
        raise HTTPException(status_code=400, detail="You cannot demote your own admin account.")

    new_role = UserRole(payload.role)
    if target.role == UserRole.admin and new_role != UserRole.admin and _count_admins(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot demote the last admin account.")

    previous_role = target.role
    target.role = new_role
    db.add(target)

    action_type = StaffActionType.demote_moderator
    if new_role == UserRole.admin:
        action_type = StaffActionType.promote_admin
    elif new_role == UserRole.moderator:
        action_type = (
            StaffActionType.promote_moderator
            if previous_role == UserRole.user
            else StaffActionType.promote_moderator
        )
    elif previous_role == UserRole.admin:
        action_type = StaffActionType.demote_admin
    else:
        action_type = StaffActionType.demote_moderator

    log_staff_action(
        db,
        actor_id=admin.id,
        target_user_id=target.id,
        action_type=action_type,
        reason=f"Role changed from {previous_role.value} to {new_role.value}",
        action_metadata={"previous_role": previous_role.value, "new_role": new_role.value},
    )
    db.commit()
    return {"ok": True, "role": new_role.value}
