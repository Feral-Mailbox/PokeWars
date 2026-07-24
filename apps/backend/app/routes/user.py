from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.dependencies import get_current_user, get_db
from app.schemas.auth import PublicPlayerProfile, UserResponse

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


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
