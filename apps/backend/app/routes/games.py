from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime
import hashlib
import redis

from app.db.models import Game, User, Map, GameStatus
from app.schemas.games import GameResponse, GameCreateRequest
from app.dependencies import get_db, get_current_user

router = APIRouter(prefix="/games", tags=["games"])
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

@router.get("/open", response_model=List[GameResponse])
def get_open_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .options(joinedload(Game.players), joinedload(Game.host))
        .filter(Game.status == GameStatus.open, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return games

@router.get("/closed", response_model=List[GameResponse])
def get_open_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .options(joinedload(Game.players), joinedload(Game.host))
        .filter(Game.status == GameStatus.closed, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return games

@router.get("/in_progress", response_model=List[GameResponse])
def get_open_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .options(joinedload(Game.players), joinedload(Game.host))
        .filter(Game.status == GameStatus.in_progress, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return games

@router.get("/completed", response_model=List[GameResponse])
def get_open_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .options(joinedload(Game.players), joinedload(Game.host))
        .filter(Game.status == GameStatus.completed, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return games

@router.post("/create", response_model=GameResponse)
def create_game(
    data: GameCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    selected_map = db.query(Map).filter(Map.name == data.map_name).first()
    if not selected_map:
        raise HTTPException(status_code=404, detail="Selected map not found")
    
    new_game = Game(
        host_id=user.id,
        game_name=data.game_name,
        map_id=selected_map.id,
        map_name=data.map_name,
        max_players=data.max_players,
        is_private=data.is_private,
        status="open",
        link="temp",
        gamemode=data.gamemode,
        starting_cash=data.starting_cash,
        cash_per_turn=data.cash_per_turn,
        max_turns=data.max_turns,
        unit_limit=data.unit_limit,
    )
    new_game.players.append(user)
    db.add(new_game)
    db.flush()
    
    hash_value = hashlib.sha256(str(new_game.id).encode()).hexdigest()
    new_game.link = hash_value
    
    db.commit()
    db.refresh(new_game)
    return new_game

@router.post("/join/{game_id}", response_model=GameResponse)
def join_game(
    game_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    game = (
        db.query(Game)
        .options(joinedload(Game.map), joinedload(Game.players), joinedload(Game.host))
        .filter(Game.id == game_id)
        .first()
    )

    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if user in game.players:
        raise HTTPException(status_code=400, detail="User already in game")

    if game.status != GameStatus.open:
        raise HTTPException(status_code=400, detail="Game not open")

    game.players.append(user)
    db.commit()
    
    if len(game.players) >= game.max_players:
        game.status = GameStatus.closed
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "player_joined")
    
    db.refresh(game)
    return game

@router.post("/start/{game_id}")
def start_game(game_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if user.id != game.host_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")
    if len(game.players) < game.max_players:
        raise HTTPException(status_code=400, detail="Game not full")

    if game.gamemode in ["Conquest", "Capture The Flag"]:
        game.status = GameStatus.preparation
    else:
        game.status = GameStatus.in_progress

    db.commit()
    redis_client.publish(f"game_updates:{game.link}", "game_started")
    return {"detail": "Game started"}

@router.get("/{link}", response_model=GameResponse)
def get_game_by_link(link: str, db: Session = Depends(get_db)):
    game = (
        db.query(Game)
        .options(joinedload(Game.map), joinedload(Game.players), joinedload(Game.host))
        .filter(Game.link == link)
        .first()
    )
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game
