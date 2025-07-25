from pydantic import BaseModel, EmailStr, ConfigDict

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

    model_config = ConfigDict(from_attributes=True)
