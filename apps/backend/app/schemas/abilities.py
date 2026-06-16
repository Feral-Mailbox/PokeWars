from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any


class AbilitySchema(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    generation: int
    effect: Optional[List[Any]] = None

    model_config = ConfigDict(from_attributes=True)
