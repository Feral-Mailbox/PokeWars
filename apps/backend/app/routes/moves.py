from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.models import Move
from app.schemas.moves import MoveSchema
from app.dependencies import get_db

router = APIRouter(prefix="/moves", tags=["moves"])

@router.get("/all", response_model=list[MoveSchema])
def get_all_moves(db: Session = Depends(get_db)):
    return db.query(Move).all()
