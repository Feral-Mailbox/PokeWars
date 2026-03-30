from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Tuple

TimedTileEffect = Tuple[int, int]

class MapDetail(BaseModel):
    id: int
    name: str
    allowed_modes: List[str]
    allowed_player_counts: List[int]
    width: int
    height: int
    tileset_names: List[str]
    tile_data: dict

    model_config = ConfigDict(from_attributes=True)


class GameMapStateSchema(BaseModel):
    id: int
    game_id: int
    map_id: int
    map: MapDetail

    weather_tiles: List[List[int | TimedTileEffect]]
    hazard_tiles: List[List[List[Tuple[int, int]]]]
    room_effect_tiles: List[List[int | TimedTileEffect]]
    terrain_effect_tiles: List[List[int | TimedTileEffect]]
    field_effect_tiles: List[List[int]]

    item_id_tiles: List[List[Optional[int]]]

    model_config = ConfigDict(from_attributes=True)
