from pydantic import BaseModel
from typing import List, Optional

class UnitSummary(BaseModel):
    id: int
    species_id: int
    form_id: Optional[int]
    name: str
    asset_folder: str
    types: List[str]
    cost: int

    class Config:
        orm_mode = True

class UnitDetail(BaseModel):
    id: int
    species_id: int
    form_id: Optional[int]
    name: str
    species: str
    asset_folder: str
    types: List[str]
    base_stats: dict
    cost: int
    evolution_cost: Optional[int]
    evolves_into: Optional[List[int]]
    is_legendary: bool
    description: Optional[str]

    class Config:
        orm_mode = True
