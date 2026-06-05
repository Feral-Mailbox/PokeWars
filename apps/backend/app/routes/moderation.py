from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import (
    ChatInfraction,
    Game,
    InfractionStatus,
    StaffActionType,
    User,
    UserRestriction,
    UserRole,
    RestrictionType,
)
from app.dependencies import (
    MOD_MUTE_MAX_HOURS,
    MOD_TEMP_BAN_MAX_DAYS,
    get_db,
    require_moderator,
    user_is_muted,
)
from app.moderation.staff_actions import apply_ban, log_staff_action
from app.schemas.moderation import (
    InfractionDetail,
    InfractionSummary,
    ModerationActionRequest,
    MuteRequest,
    TempBanRequest,
    UserModerationSummary,
)

router = APIRouter(prefix="/moderation", tags=["moderation"])


def _infraction_to_summary(infraction: ChatInfraction, db: Session) -> InfractionSummary:
    user = db.query(User).filter(User.id == infraction.user_id).first()
    game = db.query(Game).filter(Game.id == infraction.game_id).first()
    return InfractionSummary(
        id=infraction.id,
        user_id=infraction.user_id,
        username=user.username if user else "Unknown",
        game_id=infraction.game_id,
        game_link=game.link if game else None,
        censored_message=infraction.censored_message,
        severity=infraction.severity.value,
        status=infraction.status.value,
        created_at=infraction.created_at,
        matched_term_count=len(infraction.matched_terms or []),
    )


def _infraction_to_detail(infraction: ChatInfraction, db: Session) -> InfractionDetail:
    summary = _infraction_to_summary(infraction, db)
    return InfractionDetail(
        **summary.model_dump(),
        original_message=infraction.original_message,
        matched_terms=list(infraction.matched_terms or []),
        moderator_notes=infraction.moderator_notes,
        reviewed_by=infraction.reviewed_by,
        reviewed_at=infraction.reviewed_at,
    )


@router.get("/queue", response_model=list[InfractionSummary])
def get_moderation_queue(
    db: Session = Depends(get_db),
    moderator: User = Depends(require_moderator),
):
    infractions = (
        db.query(ChatInfraction)
        .filter(ChatInfraction.status == InfractionStatus.pending_review)
        .order_by(ChatInfraction.created_at.desc())
        .limit(100)
        .all()
    )
    return [_infraction_to_summary(item, db) for item in infractions]


@router.get("/infractions/{infraction_id}", response_model=InfractionDetail)
def get_infraction_detail(
    infraction_id: int,
    db: Session = Depends(get_db),
    moderator: User = Depends(require_moderator),
):
    infraction = db.query(ChatInfraction).filter(ChatInfraction.id == infraction_id).first()
    if not infraction:
        raise HTTPException(status_code=404, detail="Infraction not found")
    return _infraction_to_detail(infraction, db)


@router.get("/users/{user_id}/history", response_model=UserModerationSummary)
def get_user_moderation_history(
    user_id: int,
    db: Session = Depends(get_db),
    moderator: User = Depends(require_moderator),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    pending = (
        db.query(ChatInfraction)
        .filter(
            ChatInfraction.user_id == user_id,
            ChatInfraction.status == InfractionStatus.pending_review,
        )
        .count()
    )
    total = db.query(ChatInfraction).filter(ChatInfraction.user_id == user_id).count()

    return UserModerationSummary(
        id=target.id,
        username=target.username,
        role=target.role.value,
        is_banned=target.is_banned,
        ban_expires_at=target.ban_expires_at,
        pending_infractions=pending,
        total_infractions=total,
        is_muted=user_is_muted(target.id, db),
    )


@router.post("/infractions/{infraction_id}/dismiss")
def dismiss_infraction(
    infraction_id: int,
    payload: ModerationActionRequest,
    db: Session = Depends(get_db),
    moderator: User = Depends(require_moderator),
):
    infraction = db.query(ChatInfraction).filter(ChatInfraction.id == infraction_id).first()
    if not infraction:
        raise HTTPException(status_code=404, detail="Infraction not found")

    now = datetime.now(timezone.utc)
    infraction.status = InfractionStatus.dismissed
    infraction.reviewed_by = moderator.id
    infraction.reviewed_at = now
    infraction.moderator_notes = payload.notes
    db.add(infraction)
    log_staff_action(
        db,
        actor_id=moderator.id,
        target_user_id=infraction.user_id,
        infraction_id=infraction.id,
        action_type=StaffActionType.dismiss,
        reason=payload.reason,
    )
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/warn")
def warn_user(
    user_id: int,
    payload: ModerationActionRequest,
    db: Session = Depends(get_db),
    moderator: User = Depends(require_moderator),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    log_staff_action(
        db,
        actor_id=moderator.id,
        target_user_id=target.id,
        action_type=StaffActionType.warn,
        reason=payload.reason,
        action_metadata={"notes": payload.notes},
    )
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/mute")
def mute_user(
    user_id: int,
    payload: MuteRequest,
    db: Session = Depends(get_db),
    moderator: User = Depends(require_moderator),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role in (UserRole.moderator, UserRole.admin):
        raise HTTPException(status_code=403, detail="Cannot mute staff accounts.")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=min(payload.hours, MOD_MUTE_MAX_HOURS))
    restriction = UserRestriction(
        user_id=target.id,
        restriction_type=RestrictionType.mute,
        expires_at=expires_at,
        created_by=moderator.id,
        reason=payload.reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(restriction)
    log_staff_action(
        db,
        actor_id=moderator.id,
        target_user_id=target.id,
        action_type=StaffActionType.mute,
        reason=payload.reason,
        action_metadata={"expires_at": expires_at.isoformat(), "notes": payload.notes},
    )
    db.commit()
    return {"ok": True, "expires_at": expires_at.isoformat()}


@router.post("/users/{user_id}/temp-ban")
def temp_ban_user(
    user_id: int,
    payload: TempBanRequest,
    db: Session = Depends(get_db),
    moderator: User = Depends(require_moderator),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    expires_at = datetime.now(timezone.utc) + timedelta(days=min(payload.days, MOD_TEMP_BAN_MAX_DAYS))
    apply_ban(
        db,
        actor=moderator,
        target=target,
        reason=payload.reason,
        expires_at=expires_at,
        action_type=StaffActionType.temp_ban,
    )
    db.commit()
    return {"ok": True, "expires_at": expires_at.isoformat()}
