from app.schemas.maps import MapDetail
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Any

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

class PlayerInfo(BaseModel):
    id: int
    player_id: int
    username: str
    cash_remaining: int

    class Config:
        from_attributes = True
        
class HostInfo(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True

class GameResponse(BaseModel):
    id: int
    is_private: bool
    game_name: str
    map_name: str
    map: MapDetail
    max_players: int
    host_id: int
    players: List[PlayerInfo]
    winner_id: Optional[int]
    gamemode: str
    status: str
    current_turn: Optional[int]
    starting_cash: Optional[int]
    cash_per_turn: Optional[int]
    max_turns: Optional[int]
    unit_limit: Optional[int]
    replay_log: Optional[Any]
    link: str
    timestamp: datetime

    class Config:
        from_attributes = True

class GameStateSchema(BaseModel):
    id: int
    game_id: int
    player_id: int
    status: str
    game_units: List[dict]
    cash_remaining: int

    class Config:
        from_attributes = True
        from_attributes = True
