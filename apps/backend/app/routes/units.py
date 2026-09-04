from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.db.models import Unit
from app.schemas.units import UnitSummary
from app.dependencies import get_db

router = APIRouter(prefix="/units", tags=["units"])

@router.get("/summary", response_model=List[UnitSummary])
def get_units(db: Session = Depends(get_db)):
    units = db.query(Unit).all()
    # Guard against legacy/seed rows with null cost so one bad row cannot 500 the catalog.
    for unit in units:
        if getattr(unit, "cost", None) is None:
            unit.cost = 0
    return units
