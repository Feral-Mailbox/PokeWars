from fastapi import APIRouter, Depends
from app.schemas.auth import UserResponse
from app.dependencies import get_current_user
from app.db.models import User

router = APIRouter()

@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user
