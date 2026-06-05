from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.db.models import User
from app.schemas.auth import UserResponse
from app.dependencies import get_db, ensure_user_not_banned, clear_expired_ban

router = APIRouter()

@router.get("/me", response_model=UserResponse)
def get_current_user(request: Request, db: Session = Depends(get_db)):
    session_user_id = request.cookies.get("session_user")
    if not session_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    user = db.query(User).filter(User.id == int(session_user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    clear_expired_ban(user, db)
    ensure_user_not_banned(user)

    return user
