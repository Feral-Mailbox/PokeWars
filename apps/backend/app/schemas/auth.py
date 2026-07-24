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
    trainer_id: str
    username: str
    email: EmailStr
    avatar: str
    elo_conquest: int
    elo_war: int
    currency: int
    role: str = "user"

    model_config = ConfigDict(from_attributes=True)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        if hasattr(value, "value"):
            return value.value
        return value or "user"

    @field_validator("trainer_id", mode="before")
    @classmethod
    def normalize_trainer_id(cls, value):
        return str(value).upper() if value is not None else value


class PublicPlayerProfile(BaseModel):
    """Public profile fields safe to share by trainer_id (no email)."""

    trainer_id: str
    username: str
    avatar: str
    elo_conquest: int
    elo_war: int
    currency: int
    role: str = "user"

    model_config = ConfigDict(from_attributes=True)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        if hasattr(value, "value"):
            return value.value
        return value or "user"

    @field_validator("trainer_id", mode="before")
    @classmethod
    def normalize_trainer_id(cls, value):
        return str(value).upper() if value is not None else value
