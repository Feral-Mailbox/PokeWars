from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    avatar: str
    elo: int
    currency: int

    class Config:
        from_attributes = True  # Required for SQLAlchemy integration in Pydantic v2
