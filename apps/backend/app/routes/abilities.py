from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.models import Ability
from app.schemas.abilities import AbilitySchema
from app.dependencies import get_db

router = APIRouter(prefix="/abilities", tags=["abilities"])


@router.get("/all", response_model=list[AbilitySchema])
def get_all_abilities(db: Session = Depends(get_db)):
    return db.query(Ability).order_by(Ability.id).all()
