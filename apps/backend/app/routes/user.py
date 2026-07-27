from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models import User
from app.dependencies import get_current_user, get_db
from app.routes.auth import hash_password, verify_password
from app.schemas.auth import (
    ChangePasswordRequest,
    PublicPlayerProfile,
    UpdateEmailRequest,
    UserResponse,
)
from app.schemas.invitations import PlayerSearchResult

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me/email", response_model=UserResponse)
def update_email(
    req: UpdateEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not getattr(user, "hashed_password", None) or not verify_password(
        req.current_password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    new_email = str(req.email).strip().lower()
    if new_email == (user.email or "").strip().lower():
        return user

    taken = (
        db.query(User)
        .filter(func.lower(User.email) == new_email, User.id != user.id)
        .first()
    )
    if taken is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already taken",
        )

    user.email = new_email
    db.commit()
    db.refresh(user)
    return user


@router.patch("/me/password", response_model=UserResponse)
def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not getattr(user, "hashed_password", None) or not verify_password(
        req.current_password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    user.hashed_password = hash_password(req.new_password)
    db.commit()
    db.refresh(user)
    return user


@router.get("/players/search", response_model=list[PlayerSearchResult])
def search_players(
    q: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = q.strip()
    if not query:
        return []

    trainer_q = query.upper()
    rows = (
        db.query(User)
        .filter(
            User.id != user.id,
            or_(
                User.username.ilike(f"%{query}%"),
                User.trainer_id == trainer_q,
            ),
        )
        .order_by(User.username.asc())
        .limit(12)
        .all()
    )
    return rows


@router.get("/players/{trainer_id}", response_model=PublicPlayerProfile)
def get_player_by_trainer_id(trainer_id: str, db: Session = Depends(get_db)):
    normalized = trainer_id.strip().upper()
    if len(normalized) != 8:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )

    player = db.query(User).filter(User.trainer_id == normalized).first()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )
    return player
