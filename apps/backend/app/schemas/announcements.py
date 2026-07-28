from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateAnnouncementRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("title", "message")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    message: str
    author_id: int
    author_username: str
    created_at: datetime
    starred: bool = False

    model_config = ConfigDict(from_attributes=True)


class ClearAnnouncementsResponse(BaseModel):
    cleared: int
