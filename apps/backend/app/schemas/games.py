from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Any

class GameCreateRequest(BaseModel):
    game_name: str
    map_name: str
    max_players: int
    is_private: bool

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
    max_players: int
    host_id: int
    host: HostInfo
    players: List[PlayerInfo]
    winner_id: Optional[int]
    turns: Optional[int]
    replay_log: Optional[Any]
    link: str
    timestamp: datetime

    class Config:
        orm_mode = True
