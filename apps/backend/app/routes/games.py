from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timedelta, timezone
from collections import deque
import random
import hashlib
import json
import redis

from app.db.models import Game, User, Map, GameStatus, GameUnit, GameState, GamePlayer, Unit, Move
from app.schemas.games import GameResponse, GameCreateRequest, GameStateSchema, PlayerInfo
from app.schemas.maps import MapDetail
from app.schemas.units import GameUnitSchema, GameUnitCreateRequest
from app.dependencies import get_db, get_current_user

router = APIRouter(prefix="/games", tags=["games"])
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

TYPE_EFFECTIVENESS = {
    "normal": {"weak": [], "resist": ["rock", "steel"], "immune": ["ghost"]},
    "fire": {"weak": ["grass", "ice", "bug", "steel"], "resist": ["fire", "water", "rock", "dragon"], "immune": []},
    "water": {"weak": ["fire", "ground", "rock"], "resist": ["water", "grass", "dragon"], "immune": []},
    "electric": {"weak": ["water", "flying"], "resist": ["electric", "grass", "dragon"], "immune": ["ground"]},
    "grass": {"weak": ["water", "ground", "rock"], "resist": ["fire", "grass", "poison", "flying", "bug", "dragon", "steel"], "immune": []},
    "ice": {"weak": ["grass", "ground", "flying", "dragon"], "resist": ["fire", "water", "ice", "steel"], "immune": []},
    "fighting": {"weak": ["normal", "ice", "rock", "dark", "steel"], "resist": ["poison", "flying", "psychic", "bug", "fairy"], "immune": ["ghost"]},
    "poison": {"weak": ["grass", "fairy"], "resist": ["poison", "ground", "rock", "ghost"], "immune": ["steel"]},
    "ground": {"weak": ["fire", "electric", "poison", "rock", "steel"], "resist": ["grass", "bug"], "immune": ["flying"]},
    "flying": {"weak": ["grass", "fighting", "bug"], "resist": ["electric", "rock", "steel"], "immune": []},
    "psychic": {"weak": ["fighting", "poison"], "resist": ["psychic", "steel"], "immune": ["dark"]},
    "bug": {"weak": ["grass", "psychic", "dark"], "resist": ["fire", "fighting", "poison", "flying", "ghost", "steel", "fairy"], "immune": []},
    "rock": {"weak": ["fire", "ice", "flying", "bug"], "resist": ["fighting", "ground", "steel"], "immune": []},
    "ghost": {"weak": ["psychic", "ghost"], "resist": ["dark"], "immune": ["normal"]},
    "dragon": {"weak": ["dragon"], "resist": ["steel"], "immune": ["fairy"]},
    "dark": {"weak": ["psychic", "ghost"], "resist": ["fighting", "dark", "fairy"], "immune": []},
    "steel": {"weak": ["ice", "rock", "fairy"], "resist": ["fire", "water", "electric", "steel"], "immune": []},
    "fairy": {"weak": ["fighting", "dragon", "dark"], "resist": ["fire", "poison", "steel"], "immune": []},
}


def get_type_multiplier(move_type: str, defender_types: List[str]) -> float:
    if not move_type:
        return 1
    chart = TYPE_EFFECTIVENESS.get(str(move_type).lower())
    if not chart:
        return 1
    multiplier = 1.0
    for dtype in defender_types or []:
        key = str(dtype).lower()
        if key in chart["immune"]:
            return 0
        if key in chart["weak"]:
            multiplier *= 2
        elif key in chart["resist"]:
            multiplier *= 0.5
    return multiplier

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
        player_order=game_state.players,
        winner_id=game_state.winner_id,
        gamemode=game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=game.starting_cash,
        cash_per_turn=game.cash_per_turn,
        max_turns=game.max_turns,
        unit_limit=game.unit_limit,
        turn_seconds=game.turn_seconds,
        turn_deadline=game_state.turn_deadline,
        replay_log=game_state.replay_log,
        link=game.link,
        timestamp=game.timestamp
    )

def advance_if_expired(game: Game, state: GameState, db: Session) -> bool:
    """Advance to the next player if the turn timer elapsed. Returns True if advanced."""
    if state.status != GameStatus.in_progress or not state.turn_deadline:
        return False
    now = datetime.now(timezone.utc)
    if now < state.turn_deadline:
        return False

    # Sync all units' starting positions to current positions before advancing turn
    units_to_sync = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
    for unit in units_to_sync:
        unit.starting_x = unit.current_x
        unit.starting_y = unit.current_y

    # Reset can_move for the current player's units before advancing turn
    current_player_id = state.players[state.current_turn % len(state.players)]
    current_player_units = db.query(GameUnit).filter(
        GameUnit.game_id == game.id,
        GameUnit.user_id == current_player_id
    ).all()
    for unit in current_player_units:
        unit.can_move = True

    # Advance to next player by position in state.players (list of user_ids)
    if not state.players:
        return False

    # Increment turn counter
    if state.current_turn is None:
        state.current_turn = 0
    else:
        state.current_turn += 1
    
    # Check if game should be completed (max_turns represents full rounds, not individual player turns)
    if game.max_turns and state.current_turn >= game.max_turns * len(state.players):
        state.status = GameStatus.completed
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return True
    
    state.turn_deadline = now + timedelta(seconds=game.turn_seconds)

    compute_turn_locks(game, state, db)
    db.commit()
    redis_client.publish(f"game_updates:{game.link}", "turn_advanced")
    redis_client.publish(f"game_updates:{game.link}", "turn_started")
    return True

def movement_range_backend(start, rng, movement_costs, width, height):
    sx, sy = start
    seen = set()
    out = []
    q = deque([(sx, sy, 0)])
    dirs = [(1,0),(-1,0),(0,1),(0,-1)]
    while q:
        x, y, c = q.popleft()
        if x < 0 or y < 0 or x >= width or y >= height: 
            continue
        key = (x, y)
        if key in seen: 
            continue
        seen.add(key)
        out.append([x, y])
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                nc = c + movement_costs[ny][nx]
                if nc <= rng and (nx, ny) not in seen:
                    q.append((nx, ny, nc))
    return out

def compute_turn_locks(game: Game, state: GameState, db: Session):
    """Cache {unit_id: {origin:[x,y], tiles:[[...],...]}} for the player whose turn it is."""
    if state.current_turn is None or not state.players:
        return

    # Derive the current player from the turn counter
    current_player_id = state.players[state.current_turn % len(state.players)]

    map_obj = db.query(Map).filter_by(id=game.map_id).first()
    costs = map_obj.tile_data["movement_cost"]
    width, height = map_obj.width, map_obj.height
    units = (
        db.query(GameUnit)
        .join(Unit, Unit.id == GameUnit.unit_id)
        .filter(GameUnit.game_id == game.id, GameUnit.user_id == current_player_id)
        .all()
    )

    key = f"turnlock:{game.link}:{current_player_id}"
    redis_client.delete(key)

    # Store as a hash: field=unit_id, value=json
    for gu in units:
        gu.can_move = True
        rng = (gu.unit.base_stats or {}).get("range", 0)
        tiles = movement_range_backend((gu.starting_x, gu.starting_y), rng, costs, width, height)
        redis_client.hset(
            key, str(gu.id),
            json.dumps({"origin": [gu.starting_x, gu.starting_y], "tiles": tiles})
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
        turn_seconds=data.turn_seconds or 300,
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
        player_order=game_state.players,
        turn_deadline=game_state.turn_deadline,
        winner_id=game_state.winner_id,
        gamemode=new_game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=new_game.starting_cash,
        cash_per_turn=new_game.cash_per_turn,
        max_turns=new_game.max_turns,
        unit_limit=new_game.unit_limit,
        turn_seconds=new_game.turn_seconds,
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
        player_order=game_state.players,
        turn_deadline=None,
        winner_id=game_state.winner_id,
        gamemode=game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=game.starting_cash,
        cash_per_turn=game.cash_per_turn,
        max_turns=game.max_turns,
        unit_limit=game.unit_limit,
        turn_seconds=game.turn_seconds,
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

            if game_state.players:
                game_state.current_turn = 0
                game_state.turn_deadline = datetime.now(timezone.utc) + timedelta(seconds=game.turn_seconds)

            compute_turn_locks(game, game_state, db)
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_started")        
            redis_client.publish(f"game_updates:{game.link}", "turn_started")
            return {"detail": "Game started"}
        else:
            raise HTTPException(status_code=400, detail="Game already in progress or completed")
    else:
        game_state.status = GameStatus.in_progress

        if game_state.players:
                game_state.current_turn = 0
                game_state.turn_deadline = datetime.now(timezone.utc) + timedelta(seconds=game.turn_seconds)

        compute_turn_locks(game, game_state, db)
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_started")
        redis_client.publish(f"game_updates:{game.link}", "turn_started")
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
    advance_if_expired(game, game_state, db)

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
        player_order=game_state.players,
        turn_deadline=game_state.turn_deadline,
        winner_id=game_state.winner_id,
        gamemode=game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=game.starting_cash,
        cash_per_turn=game.cash_per_turn,
        max_turns=game.max_turns,
        unit_limit=game.unit_limit,
        turn_seconds=game.turn_seconds,
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

    # Calculate current_stats from base_stats using stat formulas
    # Assumptions: EV=0, IV=0, Nature=1
    level = 50
    current_stats = {}
    if isinstance(unit_info.base_stats, dict):
        for stat_name, base_value in unit_info.base_stats.items():
            if stat_name.lower() == "hp":
                # HP formula: floor((2 × Base × Level) / 100) + Level + 10
                current_stats[stat_name] = int((2 * base_value * level) / 100) + level + 10
            elif stat_name.lower() == "range":
                current_stats[stat_name] = base_value
            else:
                # Other stats formula: floor((2 × Base × Level) / 100 + 5) × Nature
                # With Nature = 1: floor((2 × Base × Level) / 100 + 5)
                current_stats[stat_name] = int((2 * base_value * level) / 100 + 5)

    # Step 1: Create and persist new GameUnit
    new_unit = GameUnit(
        game_id=game.id,
        unit_id=unit_data.unit_id,
        user_id=user.id,
        starting_x=unit_data.x,
        starting_y=unit_data.y,
        current_x=unit_data.x,
        current_y=unit_data.y,
        current_hp=current_stats.get('hp', unit_data.current_hp),
        level=level,
        current_stats=current_stats,
        stat_boosts=unit_data.stat_boosts,
        status_effects=unit_data.status_effects,
        is_fainted=unit_data.is_fainted,
    )
    db.add(new_unit)
    db.flush()

    # Step 2: Update player state
    player_state.cash_remaining -= unit_info.cost
    player_state.game_units.append(new_unit.id)

    # Step 3: Ensure SQLAlchemy registers state as dirty
    db.add(player_state)

    db.commit()
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


@router.get("/{link}/turnlock")
def get_turnlock(
    link: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    state = db.query(GameState).filter_by(game_id=game.id).first()

    # Return the locks for the player whose turn it is (i.e., the “frozen” sets)
    if not state.players or state.current_turn is None:
        return {}
    current_player_id = state.players[state.current_turn % len(state.players)]
    key = f"turnlock:{game.link}:{current_player_id}"
    raw = redis_client.hgetall(key)
    return {int(k): json.loads(v) for k, v in raw.items()}

@router.post("/{link}/end_turn")
def end_turn(
    link: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.in_progress:
        raise HTTPException(status_code=400, detail="Game not in progress")
    if not state.players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")

    current_player_id = state.players[state.current_turn % len(state.players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    units_to_sync = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
    for unit in units_to_sync:
        unit.starting_x = unit.current_x
        unit.starting_y = unit.current_y

    # Reset can_move for the current player's units before advancing turn
    current_player_units = db.query(GameUnit).filter(
        GameUnit.game_id == game.id,
        GameUnit.user_id == current_player_id
    ).all()
    for unit in current_player_units:
        unit.can_move = True

    state.current_turn = (state.current_turn + 1) if state.current_turn is not None else 0

    # Check if game should be completed (max_turns represents full rounds, not individual player turns)
    if game.max_turns and state.current_turn >= game.max_turns * len(state.players):
        state.status = GameStatus.completed
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return {"detail": "Game completed"}

    now = datetime.now(timezone.utc)
    state.turn_deadline = now + timedelta(seconds=game.turn_seconds)

    compute_turn_locks(game, state, db)
    db.commit()
    redis_client.publish(f"game_updates:{game.link}", "turn_advanced")
    redis_client.publish(f"game_updates:{game.link}", "turn_started")
    return {"detail": "Turn ended"}

@router.post("/{link}/execute_move")
def execute_move(
    link: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        unit_id = int(payload.get("unit_id"))
        move_id = int(payload.get("move_id"))
        target_ids = payload.get("target_ids") or []
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.in_progress:
        raise HTTPException(status_code=400, detail="Game not in progress")
    if not state.players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")

    current_player_id = state.players[state.current_turn % len(state.players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    gu = db.query(GameUnit).filter(GameUnit.id == unit_id, GameUnit.game_id == game.id).first()
    if not gu:
        raise HTTPException(status_code=404, detail="Unit not found")
    if gu.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only execute moves for your own unit")
    if not gu.can_move:
        raise HTTPException(status_code=400, detail="Unit is locked")

    move = db.query(Move).filter(Move.id == move_id).first()
    if not move:
        raise HTTPException(status_code=404, detail="Move not found")

    targets: List[GameUnit] = []
    if target_ids:
        targets = (
            db.query(GameUnit)
            .filter(GameUnit.game_id == game.id, GameUnit.id.in_(target_ids))
            .all()
        )

    targets_multiplier = 0.75 if len(targets) >= 2 else 1
    damage_results = []
    removed_ids: List[int] = []
    if targets:
        category = (move.category or "").lower()
        is_special = category == "special"
        attack_stat = "sp_attack" if is_special else "attack"
        defense_stat = "sp_defense" if is_special else "defense"
        power = move.power or 0
        attacker_types = gu.unit.types or []
        stab = 1.5 if move.type in attacker_types else 1

        for target in targets:
            attack = (gu.current_stats or {}).get(attack_stat, 0) or 0
            defense = (target.current_stats or {}).get(defense_stat, 1) or 1
            safe_defense = defense if defense > 0 else 1
            random_factor = random.randint(85, 100) / 100
            critical = 1
            type_multiplier = get_type_multiplier(move.type, getattr(target.unit, "types", None) or [])
            base = (((2 * gu.level) / 5 + 2) * power * (attack / safe_defense)) / 50 + 2
            damage = int(base * targets_multiplier * random_factor * stab * critical * type_multiplier)

            target.current_hp = max(0, (target.current_hp or 0) - damage)
            if target.current_hp <= 0:
                removed_ids.append(target.id)
            damage_results.append({"id": target.id, "damage": damage, "current_hp": target.current_hp})

    if removed_ids:
        removed_units = [t for t in targets if t.id in removed_ids]
        for unit in removed_units:
            player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=unit.user_id).first()
            if player_state and unit.id in player_state.game_units:
                player_state.game_units.remove(unit.id)
                db.add(player_state)
            db.delete(unit)

    if removed_ids:
        db.flush()
        remaining_units = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
        remaining_players = {unit.user_id for unit in remaining_units}
        if len(remaining_players) == 1:
            state.status = GameStatus.completed
            state.winner_id = next(iter(remaining_players))
            gu.can_move = False
            db.commit()
            for unit_id in removed_ids:
                redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
            redis_client.publish(f"game_updates:{game.link}", "game_completed")
            return {"ok": True, "unit_id": gu.id, "targets": damage_results, "removed_ids": removed_ids}

    gu.can_move = False
    db.flush()
    remaining_units = db.query(GameUnit).filter(
        GameUnit.game_id == game.id,
        GameUnit.user_id == current_player_id,
        GameUnit.can_move == True
    ).count()

    if remaining_units == 0:
        units_to_sync = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
        for unit in units_to_sync:
            unit.starting_x = unit.current_x
            unit.starting_y = unit.current_y

        current_player_units = db.query(GameUnit).filter(
            GameUnit.game_id == game.id,
            GameUnit.user_id == current_player_id
        ).all()
        for unit in current_player_units:
            unit.can_move = True

        state.current_turn = (state.current_turn + 1) if state.current_turn is not None else 0

        if game.max_turns and state.current_turn >= game.max_turns * len(state.players):
            state.status = GameStatus.completed
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_completed")
        else:
            now = datetime.now(timezone.utc)
            state.turn_deadline = now + timedelta(seconds=game.turn_seconds)
            compute_turn_locks(game, state, db)
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "turn_advanced")
            redis_client.publish(f"game_updates:{game.link}", "turn_started")
    else:
        db.commit()

    redis_client.publish(f"game_updates:{game.link}", "unit_locked")
    for unit_id in removed_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
    return {"ok": True, "unit_id": gu.id, "targets": damage_results, "removed_ids": removed_ids}

@router.post("/{link}/move")
def move_unit(
    link: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Expect: {"unit_id": int, "x": int, "y": int}
    try:
        unit_id = int(payload.get("unit_id"))
        x = int(payload.get("x"))
        y = int(payload.get("y"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.in_progress:
        raise HTTPException(status_code=400, detail="Game not in progress")

    # Check for player turn - derive active player from turn counter
    if not state.players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")
    current_player_id = state.players[state.current_turn % len(state.players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    # Fetch GameUnit and ownership check
    gu = db.query(GameUnit).filter(GameUnit.id == unit_id, GameUnit.game_id == game.id).first()
    if not gu:
        raise HTTPException(status_code=404, detail="Unit not found")
    if gu.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only move your own unit")
    if not gu.can_move:
        raise HTTPException(status_code=400, detail="Unit is locked")

    # Bounds check
    map_obj = db.query(Map).filter_by(id=game.map_id).first()
    if x < 0 or y < 0 or x >= map_obj.width or y >= map_obj.height:
        raise HTTPException(status_code=400, detail="Out of bounds")

    # Occupancy check (no stacking)
    occupied = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game.id, GameUnit.current_x == x, GameUnit.current_y == y, GameUnit.id != gu.id)
        .count()
    )
    if occupied:
        raise HTTPException(status_code=400, detail="Tile occupied")

    key = f"turnlock:{game.link}:{user.id}"
    lock = redis_client.hget(key, str(gu.id))
    if not lock:
        raise HTTPException(status_code=400, detail="Move set not initialized")
    lock = json.loads(lock)
    allowed = { (tx, ty) for tx, ty in lock["tiles"] }
    if (x, y) not in allowed:
        raise HTTPException(status_code=400, detail="Illegal move for this turn")

    gu.current_x = x
    gu.current_y = y
    db.commit()

    redis_client.publish(
        f"game_updates:{game.link}",
        f"unit_moved:{gu.id}:{gu.user_id}:{x}:{y}"
    )

    return {"ok": True, "unit_id": gu.id, "x": x, "y": y}

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