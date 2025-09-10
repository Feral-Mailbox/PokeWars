from app.schemas.maps import MapDetail
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import List, Optional, Any
from app.db.models import GameMode, GameStatus

class GameCreateRequest(BaseModel):
    game_name: str
    map_name: str
    max_players: int
    is_private: bool
    gamemode: str
    starting_cash: Optional[int] = None
    cash_per_turn: Optional[int] = None
    max_turns: Optional[int] = None
    unit_limit: Optional[int] = None
    turn_seconds: Optional[int] = 300

    @field_validator("turn_seconds")
    @classmethod
    def _bounds(cls, v):
        if v is None:
            return 300
        if not (30 <= v <= 86400):
            raise ValueError("turn_seconds must be between 30 and 86400")
        return v

class PlayerInfo(BaseModel):
    id: int
    player_id: int
    username: str
    cash_remaining: int
    is_ready: bool

    model_config = ConfigDict(from_attributes=True)
        
class HostInfo(BaseModel):
    id: int
    username: str

    model_config = ConfigDict(from_attributes=True)

class GameResponse(BaseModel):
    id: int
    is_private: bool
    game_name: str
    map_name: str
    map: MapDetail
    max_players: int
    host_id: int
    players: List[PlayerInfo]
    turn_deadline: Optional[datetime] = None
    winner_id: Optional[int]
    gamemode: GameMode
    status: str
    current_turn: Optional[int]
    starting_cash: Optional[int]
    cash_per_turn: Optional[int]
    max_turns: Optional[int]
    unit_limit: Optional[int]
    turn_seconds: Optional[int] = 300
    replay_log: Optional[Any]
    link: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class GameStateSchema(BaseModel):
    id: int
    game_id: int
    player_id: int
    status: str
    game_units: List[dict]
    cash_remaining: int

    model_config = ConfigDict(from_attributes=True)
