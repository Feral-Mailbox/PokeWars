from pydantic import BaseModel, EmailStr, ConfigDict, field_validator

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
    role: str = "user"

    model_config = ConfigDict(from_attributes=True)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        if hasattr(value, "value"):
            return value.value
        return value or "user"
