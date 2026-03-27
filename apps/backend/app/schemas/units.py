from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Optional

class StatBoostInstance(BaseModel):
    """Represents a single stat boost or debuff instance"""
    magnitude: int  # positive for boost, negative for debuff
    expires_turn: int  # absolute turn number when this expires

    model_config = ConfigDict(from_attributes=True)

class UnitSummary(BaseModel):
    id: int
    species_id: int
    form_id: Optional[int]
    name: str
    asset_folder: str
    types: List[str]
    cost: int
    base_stats: Dict[str, int]
    move_ids: List[int]
    portrait_credits: List[str]
    sprite_credits: List[str]
    archetype: Optional[str] = None

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
    move_ids: List[int]
    evolution_cost: Optional[int]
    evolves_into: Optional[List[int]]
    is_legendary: bool
    description: Optional[str]
    portrait_credits: List[str]
    sprite_credits: List[str]
    archetype: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class GameUnitCreateRequest(BaseModel):
    unit_id: int
    x: int
    y: int
    current_hp: int
    stat_boosts: Dict[str, List[StatBoostInstance]] = Field(default_factory=lambda: {
        "attack": [],
        "defense": [],
        "sp_attack": [],
        "sp_defense": [],
        "speed": [],
        "accuracy": [],
        "evasion": [],
        "crit": []
    })
    status_effects: List[str | int] = Field(default_factory=list)
    is_fainted: bool

class GameUnitSchema(BaseModel):
    id: int
    game_id: int
    unit_id: int
    user_id: int
    starting_x: int
    starting_y: int
    current_x: int
    current_y: int
    level: int
    current_hp: int
    current_stats: Dict[str, int]
    stat_boosts: Dict[str, List[StatBoostInstance]] = Field(default_factory=lambda: {
        "attack": [],
        "defense": [],
        "sp_attack": [],
        "sp_defense": [],
        "speed": [],
        "accuracy": [],
        "evasion": [],
        "crit": []
    })
    status_effects: List[str | int] = Field(default_factory=list)
    is_fainted: bool
    can_move: bool
    move_pp: List[int] = Field(default_factory=list)
    unit: UnitSummary

    model_config = ConfigDict(from_attributes=True)
