from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime
import hashlib
import redis

from app.db.models import Game, User, Map, GameStatus, GameUnit, GameState, GamePlayer, Unit
from app.schemas.games import GameResponse, GameCreateRequest, GameStateSchema, PlayerInfo
from app.schemas.maps import MapDetail
from app.schemas.units import GameUnitSchema, GameUnitCreateRequest
from app.dependencies import get_db, get_current_user

router = APIRouter(prefix="/games", tags=["games"])
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

def serialize_game_response(game: Game, db: Session) -> GameResponse:
    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    if not game_state:
        raise HTTPException(status_code=500, detail="Game state missing")

    player_states = db.query(GamePlayer).filter_by(game_id=game.id).all()
    players = []
    for ps in player_states:
        u = db.query(User).filter_by(id=ps.player_id).first()
        players.append(PlayerInfo(
            id=ps.id,
            player_id=ps.player_id,
            cash_remaining=ps.cash_remaining,
            username=u.username,
            is_ready=ps.is_ready
        ))

    map_obj = db.query(Map).filter_by(id=game.map_id).first()

    return GameResponse(
        id=game.id,
        status=game_state.status,
        is_private=game.is_private,
        game_name=game.game_name,
        map_name=game.map_name,
        map=MapDetail.model_validate(map_obj),
        max_players=game.max_players,
        host_id=game.host_id,
        players=players,
        winner_id=game_state.winner_id,
        gamemode=game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=game.starting_cash,
        cash_per_turn=game.cash_per_turn,
        max_turns=game.max_turns,
        unit_limit=game.unit_limit,
        replay_log=game_state.replay_log,
        link=game.link,
        timestamp=game.timestamp
    )

@router.get("/open", response_model=List[GameResponse])
def get_open_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .join(GameState, GameState.game_id == Game.id)
        .filter(GameState.status == GameStatus.open, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return [serialize_game_response(game, db) for game in games]

@router.get("/closed", response_model=List[GameResponse])
def get_closed_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .join(GameState, GameState.game_id == Game.id)
        .filter(GameState.status == GameStatus.closed, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return [serialize_game_response(game, db) for game in games]

@router.get("/in_progress", response_model=List[GameResponse])
def get_in_progress_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .join(GameState, GameState.game_id == Game.id)
        .filter(GameState.status == GameStatus.in_progress, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return [serialize_game_response(game, db) for game in games]

@router.get("/completed", response_model=List[GameResponse])
def get_completed_games(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    games = (
        db.query(Game)
        .join(GameState, GameState.game_id == Game.id)
        .filter(GameState.status == GameStatus.completed, Game.is_private == False)
        .order_by(Game.timestamp.desc())
        .all()
    )
    return [serialize_game_response(game, db) for game in games]

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
        link="temp",
        gamemode=data.gamemode,
        starting_cash=data.starting_cash,
        cash_per_turn=data.cash_per_turn,
        max_turns=data.max_turns,
        unit_limit=data.unit_limit,
    )
    db.add(new_game)
    db.flush()

    new_game.link = hashlib.sha256(str(new_game.id).encode()).hexdigest()

    game_state = GameState(
        game_id=new_game.id,
        status=GameStatus.open,
        current_turn=0,
        players=[user.id],
        replay_log=[],
        winner_id=None
    )
    db.add(game_state)

    player_state = GamePlayer(
        game_id=new_game.id,
        player_id=user.id,
        cash_remaining=data.starting_cash or 0,
        game_units=[]
    )
    db.add(player_state)

    db.commit()
    db.refresh(new_game)

    return GameResponse(
        id=new_game.id,
        status=game_state.status,
        is_private=new_game.is_private,
        game_name=new_game.game_name,
        map_name=new_game.map_name,
        map=MapDetail.model_validate(selected_map),
        max_players=new_game.max_players,
        host_id=user.id,
        players=[PlayerInfo(
            id=player_state.id,
            player_id=user.id,
            cash_remaining=player_state.cash_remaining,
            username=user.username,
            is_ready=player_state.is_ready
        )],
        winner_id=game_state.winner_id,
        gamemode=new_game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=new_game.starting_cash,
        cash_per_turn=new_game.cash_per_turn,
        max_turns=new_game.max_turns,
        unit_limit=new_game.unit_limit,
        replay_log=game_state.replay_log,
        link=new_game.link,
        timestamp=new_game.timestamp
    )

@router.post("/join/{game_id}", response_model=GameResponse)
def join_game(
    game_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    if not game_state:
        raise HTTPException(status_code=404, detail="Game state not found")

    if user.id in game_state.players:
        raise HTTPException(status_code=400, detail="User already in game")

    if game_state.status != GameStatus.open:
        raise HTTPException(status_code=400, detail="Game not open")

    if len(game_state.players) >= game.max_players:
        raise HTTPException(status_code=400, detail="Game is full")

    game_state.players.append(user.id)

    player_state = GamePlayer(
        game_id=game.id,
        player_id=user.id,
        cash_remaining=game.starting_cash or 0,
        game_units=[]
    )
    db.add(player_state)

    if len(game_state.players) >= game.max_players:
        game_state.status = GameStatus.closed
        redis_client.publish(f"game_updates:{game.link}", "player_joined")

    db.commit()
    db.refresh(game)

    player_states = db.query(GamePlayer).filter_by(game_id=game.id).all()
    players = []
    for ps in player_states:
        user_obj = db.query(User).filter_by(id=ps.player_id).first()
        players.append(PlayerInfo(
            id=ps.id,
            player_id=ps.player_id,
            cash_remaining=ps.cash_remaining,
            username=user_obj.username,
            is_ready=ps.is_ready
        ))

    return GameResponse(
        id=game.id,
        status=game_state.status,
        is_private=game.is_private,
        game_name=game.game_name,
        map_name=game.map_name,
        map=MapDetail.model_validate(game.map),
        max_players=game.max_players,
        host_id=game.host_id,
        players=players,
        winner_id=game_state.winner_id,
        gamemode=game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=game.starting_cash,
        cash_per_turn=game.cash_per_turn,
        max_turns=game.max_turns,
        unit_limit=game.unit_limit,
        replay_log=game_state.replay_log,
        link=game.link,
        timestamp=game.timestamp
    )

@router.post("/start/{game_id}")
def start_game(
    game_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if user.id != game.host_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")

    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    if not game_state:
        raise HTTPException(status_code=404, detail="Game state not found")

    if len(game_state.players) < game.max_players:
        raise HTTPException(status_code=400, detail="Game not full")

    # Consolidated logic for all modes
    if game.gamemode in ["Conquest", "Capture The Flag"]:
        if game_state.status == GameStatus.closed:
            game_state.status = GameStatus.preparation
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_preparation")
            return {"detail": "Game moved to preparation phase"}
        elif game_state.status == GameStatus.preparation:
            game_state.status = GameStatus.in_progress
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_started")
            return {"detail": "Game started"}
        else:
            raise HTTPException(status_code=400, detail="Game already in progress or completed")
    else:
        game_state.status = GameStatus.in_progress
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_started")
        return {"detail": "Game started"}

@router.get("/{link}", response_model=GameResponse)
def get_game_by_link(
    link: str,
    db: Session = Depends(get_db)
):
    game = (
        db.query(Game)
        .options(joinedload(Game.map), joinedload(Game.player_states))
        .filter(Game.link == link)
        .first()
    )
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    player_states = db.query(GamePlayer).filter_by(game_id=game.id).all()
    players = []
    for ps in player_states:
        user_obj = db.query(User).filter_by(id=ps.player_id).first()
        players.append(PlayerInfo(
            id=ps.id,
            player_id=ps.player_id,
            cash_remaining=ps.cash_remaining,
            username=user_obj.username,
            is_ready=ps.is_ready
        ))

    return GameResponse(
        id=game.id,
        status=game_state.status,
        is_private=game.is_private,
        game_name=game.game_name,
        map_name=game.map_name,
        map=MapDetail.model_validate(game.map),
        max_players=game.max_players,
        host_id=game.host_id,
        players=players,
        winner_id=game_state.winner_id,
        gamemode=game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=game.starting_cash,
        cash_per_turn=game.cash_per_turn,
        max_turns=game.max_turns,
        unit_limit=game.unit_limit,
        replay_log=game_state.replay_log,
        link=game.link,
        timestamp=game.timestamp
    )

@router.get("/{link}/player")
def get_player_state(
    link: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=user.id).first()
    if not state:
        raise HTTPException(status_code=404, detail="Player state not found")

    return {
        "cash_remaining": state.cash_remaining,
        "game_units": state.game_units,
        "is_ready": state.is_ready
    }

@router.post("/{link}/player/ready")
def toggle_ready_state(
    link: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = db.query(Game).filter_by(link=link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.gamemode not in ["Conquest", "Capture The Flag"]:
        raise HTTPException(status_code=400, detail="This game mode does not support readiness toggling")

    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    if game_state.status != GameStatus.preparation:
        raise HTTPException(status_code=400, detail="You may only toggle readiness during the preparation phase")

    player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=user.id).first()
    if not player_state:
        raise HTTPException(status_code=404, detail="Player not found")

    # Toggle the boolean
    player_state.is_ready = not player_state.is_ready
    db.commit()

    redis_client.publish(f"game_updates:{game.link}", "player_ready")
    return {"ready": player_state.is_ready}

@router.get("/{link}/units", response_model=List[GameUnitSchema])
def get_game_units(
    link: str,
    db: Session = Depends(get_db)
):
    return (
        db.query(GameUnit)
        .join(Game)
        .options(joinedload(GameUnit.unit))
        .filter(Game.link == link)
        .all()
    )

@router.post("/{link}/units/place", response_model=GameUnitSchema)
def place_unit(
    link: str,
    unit_data: GameUnitCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    game = db.query(Game).filter_by(link=link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=user.id).first()
    if not player_state:
        raise HTTPException(status_code=404, detail="Player state not found")

    unit_info = db.query(Unit).filter_by(id=unit_data.unit_id).first()
    if not unit_info:
        raise HTTPException(status_code=404, detail="Unit not found")

    if unit_info.cost > player_state.cash_remaining:
        raise HTTPException(status_code=400, detail="Not enough cash")

    # Step 1: Create and persist new GameUnit
    new_unit = GameUnit(
        game_id=game.id,
        unit_id=unit_data.unit_id,
        user_id=user.id,
        x=unit_data.x,
        y=unit_data.y,
        current_hp=unit_data.current_hp,
        stat_boosts=unit_data.stat_boosts,
        status_effects=unit_data.status_effects,
        is_fainted=unit_data.is_fainted,
    )
    db.add(new_unit)
    db.flush()  # Get new_unit.id before assigning

    # Step 2: Update player state
    player_state.cash_remaining -= unit_info.cost
    player_state.game_units.append(new_unit.id)

    # Step 3: Ensure SQLAlchemy registers state as dirty
    db.add(player_state)

    db.commit()  # Now commit everything
    db.refresh(new_unit)

    return new_unit

@router.delete("/{link}/units/remove/{unit_id}")
def remove_unit(
    link: str,
    unit_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    game = db.query(Game).filter_by(link=link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    unit = db.query(GameUnit).filter_by(id=unit_id, game_id=game.id, user_id=user.id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    unit_info = db.query(Unit).filter_by(id=unit.unit_id).first()
    if not unit_info:
        raise HTTPException(status_code=404, detail="Unit metadata not found")

    player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=user.id).first()
    if not player_state:
        raise HTTPException(status_code=404, detail="Player state not found")

    player_state.cash_remaining += unit_info.cost
    if unit.id in player_state.game_units:
        player_state.game_units.remove(unit.id)

    db.add(player_state)

    db.delete(unit)
    db.commit()
    return {"detail": "Unit removed and cash refunded"}

@router.get("/{link}/state", response_model=GameStateSchema)
def get_game_state(
    link: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    state = db.query(GameState).filter_by(game_id=game.id, player_id=user.id).first()
    if not state:
        raise HTTPException(status_code=404, detail="Game state not found")
    return state

@router.patch("/{link}/state", response_model=GameStateSchema)
def update_game_state(
    link: str,
    patch: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    state = db.query(GameState).filter_by(game_id=game.id, player_id=user.id).first()
    if not state:
        raise HTTPException(status_code=404, detail="Game state not found")

    for key, value in patch.items():
        if hasattr(state, key):
            setattr(state, key, value)

    db.commit()
    db.refresh(state)
    return state