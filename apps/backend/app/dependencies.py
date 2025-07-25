# app/dependencies.py
from fastapi import Depends, Cookie, HTTPException
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.database import get_db as _get_db

def get_db():
    yield from _get_db()

def get_current_user(session_user: str = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    if session_user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(User).filter(User.id == int(session_user)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
