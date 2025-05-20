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

    class Config:
        orm_mode = True
        
class HostInfo(BaseModel):
    id: int
    username: str

    class Config:
        orm_mode = True

class GameResponse(BaseModel):
    id: int
    status: str
    is_private: bool
    game_name: str
    map_name: str
    map: MapDetail
    max_players: int
    host_id: int
    host: HostInfo
    players: List[PlayerInfo]
    winner_id: Optional[int]
    gamemode: str
    current_turn: Optional[int]
    starting_cash: Optional[int]
    cash_per_turn: Optional[int]
    max_turns: Optional[int]
    unit_limit: Optional[int]
    replay_log: Optional[Any]
    link: str
    timestamp: datetime

    class Config:
        orm_mode = True
