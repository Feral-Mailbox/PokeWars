from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Optional

class UnitSummary(BaseModel):
    id: int
    species_id: int
    form_id: Optional[int]
    name: str
    asset_folder: str
    types: List[str]
    cost: int
    base_stats: Dict[str, int]

    model_config = ConfigDict(from_attributes=True)

class UnitDetail(BaseModel):
    id: int
    species_id: int
    form_id: Optional[int]
    name: str
    species: str
    asset_folder: str
    types: List[str]
    base_stats: Dict[str, int]
    cost: int
    evolution_cost: Optional[int]
    evolves_into: Optional[List[int]]
    is_legendary: bool
    description: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class GameUnitCreateRequest(BaseModel):
    unit_id: int
    x: int
    y: int
    current_hp: int
    stat_boosts: Dict[str, int]
    status_effects: List[str]
    is_fainted: bool

class GameUnitSchema(BaseModel):
    id: int
    game_id: int
    unit_id: int
    user_id: int
    x: int
    y: int
    current_hp: int
    stat_boosts: Dict[str, int]
    status_effects: List[str]
    is_fainted: bool
    unit: UnitSummary

    model_config = ConfigDict(from_attributes=True)
