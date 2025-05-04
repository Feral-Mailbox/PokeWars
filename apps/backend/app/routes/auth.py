from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from app.db.models import User, SessionLocal
from app.schemas.auth import RegisterRequest, LoginRequest, UserResponse
from app.utils.security import hash_password, verify_password
from datetime import timedelta
import os

router = APIRouter()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

SESSION_EXPIRATION = timedelta(
    hours=int(os.getenv("SESSION_EXPIRE_HOURS", "24"))
).total_seconds()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/register", response_model=UserResponse)
def register(req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
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
        max_age=SESSION_EXPIRATION,
    )

    return user

@router.post("/login", response_model=UserResponse)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(user.hashed_password, req.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    response.set_cookie(
        key="session_user",
        value=str(user.id),
        httponly=True,
        max_age=SESSION_EXPIRATION,
    )
    
    return user

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("session_user")
    return {"detail": "Logged out"}
