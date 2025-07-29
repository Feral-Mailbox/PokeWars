from pydantic import BaseModel, ConfigDict
from typing import Optional, List


class MoveSchema(BaseModel):
    id: int
    name: str
    description: Optional[str]
    type: str
    category: str
    power: Optional[int]
    accuracy: Optional[int]
    pp: Optional[int]
    makes_contact: Optional[bool]
    affected_by_protect: Optional[bool]
    affected_by_magic_coat: Optional[bool]
    affected_by_snatch: Optional[bool]
    affected_by_mirror_move: Optional[bool]
    affected_by_kings_rock: Optional[bool]
    range: Optional[str]
    targeting: Optional[str]
    cooldown: Optional[int]
    effects: List[str]

    model_config = ConfigDict(from_attributes=True)
