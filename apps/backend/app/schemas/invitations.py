from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateInvitationRequest(BaseModel):
    game_id: int
    invitee_id: Optional[int] = None
    invitee_username: Optional[str] = None
    invitee_trainer_id: Optional[str] = None


class InvitationResponse(BaseModel):
    id: int
    game_id: int
    game_name: str
    game_link: str
    gamemode: str
    inviter_id: int
    inviter_username: str
    invitee_id: int
    invitee_username: str
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value):
        if hasattr(value, "value"):
            return value.value
        return value


class InboxResponse(BaseModel):
    invitations: list[InvitationResponse]
    pending_count: int = Field(ge=0)


class PlayerSearchResult(BaseModel):
    id: int
    trainer_id: str
    username: str
    avatar: str
    elo_conquest: int
    elo_war: int
    role: str = "user"

    model_config = ConfigDict(from_attributes=True)

    @field_validator("trainer_id", mode="before")
    @classmethod
    def normalize_trainer_id(cls, value):
        return str(value).upper() if value is not None else value

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        if hasattr(value, "value"):
            return value.value
        return value or "user"
