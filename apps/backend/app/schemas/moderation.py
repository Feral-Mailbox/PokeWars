from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

MOD_MUTE_MAX_HOURS = 72
MOD_TEMP_BAN_MAX_DAYS = 7


class InfractionSummary(BaseModel):
    id: int
    user_id: int
    username: str
    game_id: int
    game_link: Optional[str] = None
    censored_message: str
    severity: str
    status: str
    created_at: datetime
    matched_term_count: int

    model_config = ConfigDict(from_attributes=True)


class InfractionDetail(InfractionSummary):
    original_message: str
    matched_terms: list[str]
    moderator_notes: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None


class UserModerationSummary(BaseModel):
    id: int
    username: str
    role: str
    is_banned: bool
    ban_expires_at: Optional[datetime] = None
    pending_infractions: int
    total_infractions: int
    is_muted: bool


class StaffMember(BaseModel):
    id: int
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class StaffActionRecord(BaseModel):
    id: int
    actor_id: int
    actor_username: str
    target_user_id: Optional[int] = None
    target_username: Optional[str] = None
    infraction_id: Optional[int] = None
    action_type: str
    reason: Optional[str] = None
    action_metadata: Optional[Any] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModerationActionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=1000)


class MuteRequest(ModerationActionRequest):
    hours: int = Field(ge=1, le=MOD_MUTE_MAX_HOURS)


class TempBanRequest(ModerationActionRequest):
    days: int = Field(ge=1, le=MOD_TEMP_BAN_MAX_DAYS)


class AdminBanRequest(ModerationActionRequest):
    permanent: bool = False
    days: Optional[int] = Field(default=None, ge=1, le=365)


class RoleChangeRequest(BaseModel):
    role: Literal["user", "moderator", "admin"]
