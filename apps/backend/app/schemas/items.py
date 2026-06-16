from pydantic import BaseModel, ConfigDict
from typing import Optional, List


class ItemSchema(BaseModel):
    id: int
    name: str
    slug: str
    category: str
    cost: int
    description: Optional[str]
    effects: List[str]
    natural_gift_type: Optional[str]
    natural_gift_power: Optional[int]
    flavor: Optional[str]
    boost_type: Optional[str]

    model_config = ConfigDict(from_attributes=True)
