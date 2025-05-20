from pydantic import BaseModel
from typing import List

class MapDetail(BaseModel):
    id: int
    name: str
    allowed_modes: List[str]
    width: int
    height: int
    tileset_name: str
    tile_data: dict

    class Config:
        orm_mode = True
