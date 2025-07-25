from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.models import Map
from app.schemas.maps import MapDetail
from app.dependencies import get_db

router = APIRouter(prefix="/maps", tags=["maps"])

@router.get("/official", response_model=list[MapDetail])
def get_official_maps(db: Session = Depends(get_db)):
    return db.query(Map).filter(Map.is_official == True).all()
