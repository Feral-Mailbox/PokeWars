from pydantic import BaseModel

class MapDetail(BaseModel):
    id: int
    name: str
    width: int
    height: int
    tileset_name: str
    tile_data: dict

    class Config:
        orm_mode = True
