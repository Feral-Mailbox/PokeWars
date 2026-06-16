from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.models import Item
from app.schemas.items import ItemSchema
from app.dependencies import get_db

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/all", response_model=list[ItemSchema])
def get_all_items(
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Item)
    if category:
        query = query.filter(Item.category == category)
    return query.all()
