from datetime import datetime, timedelta, timezone
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import (
    Game,
    GameInvitation,
    GameState,
    GameStatus,
    InvitationStatus,
    User,
)
from app.dependencies import get_current_user, get_db
from app.routes.games import publish_system_log_event, seat_user_in_open_game
from app.routes.ws import publish_user_ws_event
from app.schemas.invitations import (
    CreateInvitationRequest,
    InboxResponse,
    InvitationResponse,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])
logger = logging.getLogger("invitations")

INVITATION_TTL_SECONDS = int(os.getenv("INVITATION_TTL_SECONDS", "180"))


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _invitation_payload(invitation: GameInvitation, game: Game, inviter: User, invitee: User) -> dict:
    return {
        "id": invitation.id,
        "game_id": game.id,
        "game_name": game.game_name,
        "game_link": game.link,
        "gamemode": str(game.gamemode.value if hasattr(game.gamemode, "value") else game.gamemode),
        "inviter_id": inviter.id,
        "inviter_username": inviter.username,
        "invitee_id": invitee.id,
        "invitee_username": invitee.username,
        "status": invitation.status.value if hasattr(invitation.status, "value") else str(invitation.status),
        "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        "responded_at": invitation.responded_at.isoformat() if invitation.responded_at else None,
    }


def _to_response(invitation: GameInvitation, game: Game, inviter: User, invitee: User) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        game_id=game.id,
        game_name=game.game_name,
        game_link=game.link,
        gamemode=str(game.gamemode.value if hasattr(game.gamemode, "value") else game.gamemode),
        inviter_id=inviter.id,
        inviter_username=inviter.username,
        invitee_id=invitee.id,
        invitee_username=invitee.username,
        status=invitation.status,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        responded_at=invitation.responded_at,
    )


def _notify_users(user_ids: list[int], action: str, invitation_dict: dict) -> None:
    payload = {
        "event": "invitation",
        "action": action,
        "invitation": invitation_dict,
    }
    for uid in {int(uid) for uid in user_ids}:
        publish_user_ws_event(uid, payload)


def _resolve_invitee(req: CreateInvitationRequest, db: Session) -> User:
    if req.invitee_id is not None:
        invitee = db.query(User).filter(User.id == req.invitee_id).first()
        if invitee:
            return invitee
        raise HTTPException(status_code=404, detail="Player not found")

    if req.invitee_trainer_id:
        trainer_id = req.invitee_trainer_id.strip().upper()
        invitee = db.query(User).filter(User.trainer_id == trainer_id).first()
        if invitee:
            return invitee
        raise HTTPException(status_code=404, detail="Player not found")

    if req.invitee_username:
        username = req.invitee_username.strip()
        invitee = (
            db.query(User)
            .filter(User.username.ilike(username))
            .first()
        )
        if invitee:
            return invitee
        raise HTTPException(status_code=404, detail="Player not found")

    raise HTTPException(
        status_code=400,
        detail="Provide invitee_id, invitee_username, or invitee_trainer_id",
    )


def _effective_expires_at(invitation: GameInvitation) -> datetime | None:
    expires = _as_utc(invitation.expires_at)
    if expires is not None:
        return expires
    created = _as_utc(invitation.created_at)
    if created is None:
        return None
    return created + timedelta(seconds=INVITATION_TTL_SECONDS)


def _log_game_chat(game: Game, db: Session, message: str) -> None:
    state = db.query(GameState).filter_by(game_id=game.id).first()
    publish_system_log_event(game.link, message, state, db)


def _expire_invitation(
    invitation: GameInvitation,
    db: Session,
    *,
    commit: bool = False,
) -> None:
    if invitation.status != InvitationStatus.pending:
        return

    now = datetime.now(timezone.utc)
    invitation.status = InvitationStatus.expired
    invitation.responded_at = now

    game = db.query(Game).filter(Game.id == invitation.game_id).first()
    inviter = db.query(User).filter(User.id == invitation.inviter_id).first()
    invitee = db.query(User).filter(User.id == invitation.invitee_id).first()
    if game and invitee:
        _log_game_chat(game, db, f"Invitation to {invitee.username} timed out")
    if commit:
        db.commit()
        db.refresh(invitation)
    if game and inviter and invitee:
        payload = _invitation_payload(invitation, game, inviter, invitee)
        _notify_users([invitee.id, inviter.id], "expired", payload)


def expire_due_invitations(db: Session) -> int:
    """Mark timed-out pending invitations as expired and announce in game chat."""
    now = datetime.now(timezone.utc)
    pending = (
        db.query(GameInvitation)
        .filter(GameInvitation.status == InvitationStatus.pending)
        .all()
    )
    expired = 0
    for invitation in pending:
        expires = _effective_expires_at(invitation)
        if expires is None or expires > now:
            continue
        _expire_invitation(invitation, db, commit=False)
        expired += 1
    if expired:
        db.commit()
    return expired


def _ensure_invitation_still_pending(invitation: GameInvitation, db: Session) -> None:
    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=400, detail="Invitation is no longer pending")
    expires = _effective_expires_at(invitation)
    if expires is not None and expires <= datetime.now(timezone.utc):
        _expire_invitation(invitation, db, commit=True)
        raise HTTPException(status_code=400, detail="Invitation has expired")


@router.get("/inbox", response_model=InboxResponse)
def get_inbox(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expire_due_invitations(db)
    rows = (
        db.query(GameInvitation)
        .filter(GameInvitation.invitee_id == user.id)
        .order_by(GameInvitation.created_at.desc())
        .limit(50)
        .all()
    )
    invitations: list[InvitationResponse] = []
    pending_count = 0
    for invitation in rows:
        game = db.query(Game).filter(Game.id == invitation.game_id).first()
        inviter = db.query(User).filter(User.id == invitation.inviter_id).first()
        invitee = db.query(User).filter(User.id == invitation.invitee_id).first()
        if not game or not inviter or not invitee:
            continue
        if invitation.status == InvitationStatus.pending:
            pending_count += 1
        invitations.append(_to_response(invitation, game, inviter, invitee))
    return InboxResponse(invitations=invitations, pending_count=pending_count)


@router.post("", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(
    req: CreateInvitationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expire_due_invitations(db)
    game = db.query(Game).filter(Game.id == req.game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.host_id != user.id:
        raise HTTPException(status_code=403, detail="Only the host can invite players")

    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    if not game_state or game_state.status != GameStatus.open:
        raise HTTPException(status_code=400, detail="Game is not accepting players")

    if len(game_state.players or []) >= game.max_players:
        raise HTTPException(status_code=400, detail="Game is full")

    invitee = _resolve_invitee(req, db)
    if invitee.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot invite yourself")

    if invitee.id in (game_state.players or []):
        raise HTTPException(status_code=400, detail="Player is already in this game")

    existing = (
        db.query(GameInvitation)
        .filter(
            GameInvitation.game_id == game.id,
            GameInvitation.invitee_id == invitee.id,
            GameInvitation.status == InvitationStatus.pending,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Invitation already pending")

    now = datetime.now(timezone.utc)
    invitation = GameInvitation(
        game_id=game.id,
        inviter_id=user.id,
        invitee_id=invitee.id,
        status=InvitationStatus.pending,
        created_at=now,
        expires_at=now + timedelta(seconds=INVITATION_TTL_SECONDS),
    )
    db.add(invitation)
    _log_game_chat(game, db, f"{user.username} invited {invitee.username}")
    db.commit()
    db.refresh(invitation)

    payload = _invitation_payload(invitation, game, user, invitee)
    _notify_users([invitee.id, user.id], "created", payload)
    return _to_response(invitation, game, user, invitee)


@router.post("/{invitation_id}/accept", response_model=InvitationResponse)
def accept_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expire_due_invitations(db)
    invitation = db.query(GameInvitation).filter(GameInvitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.invitee_id != user.id:
        raise HTTPException(status_code=403, detail="Not your invitation")
    _ensure_invitation_still_pending(invitation, db)

    game = db.query(Game).filter(Game.id == invitation.game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    if not game_state:
        raise HTTPException(status_code=404, detail="Game state not found")

    seat_user_in_open_game(game, game_state, user, db)

    invitation.status = InvitationStatus.accepted
    invitation.responded_at = datetime.now(timezone.utc)

    if game_state.status != GameStatus.open:
        pending = (
            db.query(GameInvitation)
            .filter(
                GameInvitation.game_id == game.id,
                GameInvitation.status == InvitationStatus.pending,
                GameInvitation.id != invitation.id,
            )
            .all()
        )
        for other in pending:
            other.status = InvitationStatus.expired
            other.responded_at = datetime.now(timezone.utc)
            other_invitee = db.query(User).filter(User.id == other.invitee_id).first()
            if other_invitee:
                _log_game_chat(game, db, f"Invitation to {other_invitee.username} expired")

    db.commit()
    db.refresh(invitation)

    inviter = db.query(User).filter(User.id == invitation.inviter_id).first()
    invitee = user
    if not inviter:
        raise HTTPException(status_code=404, detail="Inviter not found")

    payload = _invitation_payload(invitation, game, inviter, invitee)
    _notify_users([invitee.id, inviter.id], "accepted", payload)
    return _to_response(invitation, game, inviter, invitee)


@router.post("/{invitation_id}/decline", response_model=InvitationResponse)
def decline_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expire_due_invitations(db)
    invitation = db.query(GameInvitation).filter(GameInvitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.invitee_id != user.id:
        raise HTTPException(status_code=403, detail="Not your invitation")
    _ensure_invitation_still_pending(invitation, db)

    invitation.status = InvitationStatus.declined
    invitation.responded_at = datetime.now(timezone.utc)

    game = db.query(Game).filter(Game.id == invitation.game_id).first()
    inviter = db.query(User).filter(User.id == invitation.inviter_id).first()
    invitee = user
    if not game or not inviter:
        raise HTTPException(status_code=404, detail="Invitation references missing data")

    _log_game_chat(game, db, f"{invitee.username} declined the invitation")
    db.commit()
    db.refresh(invitation)

    payload = _invitation_payload(invitation, game, inviter, invitee)
    _notify_users([invitee.id, inviter.id], "declined", payload)
    return _to_response(invitation, game, inviter, invitee)


@router.post("/{invitation_id}/cancel", response_model=InvitationResponse)
def cancel_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Invitee cancel (= decline) or host cancel of a pending invite."""
    expire_due_invitations(db)
    invitation = db.query(GameInvitation).filter(GameInvitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    _ensure_invitation_still_pending(invitation, db)

    is_invitee = invitation.invitee_id == user.id
    is_inviter = invitation.inviter_id == user.id
    if not is_invitee and not is_inviter:
        raise HTTPException(status_code=403, detail="Not your invitation")

    game = db.query(Game).filter(Game.id == invitation.game_id).first()
    inviter = db.query(User).filter(User.id == invitation.inviter_id).first()
    invitee = db.query(User).filter(User.id == invitation.invitee_id).first()
    if not game or not inviter or not invitee:
        raise HTTPException(status_code=404, detail="Invitation references missing data")

    if is_invitee:
        invitation.status = InvitationStatus.declined
        action = "declined"
        chat_message = f"{invitee.username} declined the invitation"
    else:
        invitation.status = InvitationStatus.cancelled
        action = "cancelled"
        chat_message = f"{inviter.username} cancelled the invitation to {invitee.username}"

    invitation.responded_at = datetime.now(timezone.utc)
    _log_game_chat(game, db, chat_message)
    db.commit()
    db.refresh(invitation)

    payload = _invitation_payload(invitation, game, inviter, invitee)
    _notify_users([invitee.id, inviter.id], action, payload)
    return _to_response(invitation, game, inviter, invitee)
