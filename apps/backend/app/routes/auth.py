from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.db.models import User
from app.schemas.auth import RegisterRequest, LoginRequest, UserResponse
from app.dependencies import get_db
from datetime import timedelta
from passlib.context import CryptContext
from pydantic import ValidationError
import os
import logging

router = APIRouter()
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger("auth")
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

SESSION_EXPIRATION = int(timedelta(
    hours=int(os.getenv("SESSION_EXPIRE_HOURS", "24"))
).total_seconds())

COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)

def hash_password(password: str) -> str:
    return pwd.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd.verify(plain_password, hashed_password)

@router.post("/register", response_model=UserResponse)
def register(req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    # Ensures registering user's username and email are not taken
    if db.query(User).filter((User.username == req.username) | (User.email == req.email)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already taken")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        avatar="default.png",
        elo=1000,
        currency=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response.set_cookie(
        key="session_user",
        value=str(user.id),
        httponly=True,
        samesite="none",
        max_age=SESSION_EXPIRATION,
        path="/",
        secure=True,
        domain=COOKIE_DOMAIN if COOKIE_DOMAIN else None, 
    )

    return UserResponse.model_validate(user, from_attributes=True)

@router.post("/login", response_model=UserResponse)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    print("DEBUG login user:", user)

    # Guard against user or hash missing
    if not user or not getattr(user, "hashed_password", None):
        # Don't leak user existence — return 401
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Guard: verification exceptions (legacy/plain hashes, bcrypt issues, etc.)
    try:
        ok = verify_password(req.password, user.hashed_password)
    except Exception as e:
        logger.exception("Password verification failed for user '%s'", req.username)
        # Treat as invalid credentials rather than 500
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from e

    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    response.set_cookie(
        key="session_user",
        value=str(user.id),
        httponly=True,
        samesite="none",
        max_age=SESSION_EXPIRATION,
        path="/",
        secure=True,
        domain=COOKIE_DOMAIN if COOKIE_DOMAIN else None,
    )

    # Guard: schema/serialization errors -> convert to 500 w/ clear log or 422/500
    try:
        return UserResponse.model_validate(user, from_attributes=True)
    except ValidationError as ve:
        logger.exception("UserResponse validation failed for user id=%s", user.id)
        # If you prefer a 500 here:
        raise HTTPException(status_code=500, detail="User serialization failed")

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="session_user",
        path="/",
        domain=COOKIE_DOMAIN if COOKIE_DOMAIN else None,
        samesite="none",
        secure=True,
        httponly=True,
    )
    return {"detail": "Logged out"}
