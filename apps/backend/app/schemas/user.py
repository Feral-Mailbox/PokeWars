from pydantic import BaseModel, ConfigDict

class UserOut(BaseModel):
    id: int
    username: str

    model_config = ConfigDict(from_attributes=True)
