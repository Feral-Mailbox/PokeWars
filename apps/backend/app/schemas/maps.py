from pydantic import BaseModel
from typing import List

class MapDetail(BaseModel):
    id: int
    name: str
    allowed_modes: List[str]
    allowed_player_counts: List[int]
    width: int
    height: int
    tileset_name: str
    tile_data: dict

    class Config:
        orm_mode = True
