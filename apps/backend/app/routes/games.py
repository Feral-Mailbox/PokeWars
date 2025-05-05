from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime

from app.db.models import Game, User, GameStatus
from app.schemas.games import GameResponse, GameCreateRequest
from app.dependencies import get_db, get_current_user

router = APIRouter(prefix="/games", tags=["games"])

@router.get("/open", response_model=List[GameResponse])
def get_open_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .options(joinedload(Game.players), joinedload(Game.host))
        .filter(Game.status == GameStatus.open, Game.is_private == False)
        .limit(10)
        .all()
    )
    return games

@router.post("/create", response_model=GameResponse)
def create_game(
    data: GameCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    new_game = Game(
        host_id=user.id,
        game_name=data.game_name,
        map_name=data.map_name,
        max_players=data.max_players,
        is_private=data.is_private,
        status="open"
    )
    new_game.players.append(user)
    db.add(new_game)
    db.commit()
    db.refresh(new_game)
    return new_game