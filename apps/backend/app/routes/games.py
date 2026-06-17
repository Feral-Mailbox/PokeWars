from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timedelta, timezone
from collections import deque
import random
import hashlib
import json
import re
import redis

from app.db.models import Game, User, Map, GameStatus, GameUnit, GameState, GamePlayer, Unit, Move, GameMapState, Ability, Item
from app.schemas.games import GameResponse, GameCreateRequest, GameStateSchema, PlayerInfo
from app.schemas.maps import MapDetail, GameMapStateSchema
from app.schemas.units import (
    GameUnitSchema,
    GameUnitCreateRequest,
    GameUnitChangeItemRequest,
    GameUnitChangeItemResponse,
    GameUnitChangeAbilityRequest,
    GameUnitChangeAbilityResponse,
)
from app.dependencies import get_db, get_current_user, ensure_user_can_chat
from app.moderation.service import apply_chat_moderation
from app.map_movement import (
    build_movement_cost_grid,
    get_grass_incoming_accuracy_multiplier,
    get_tile_defense_multiplier,
    is_stump_tile,
    movement_range_with_terrain,
    resolve_movement_destination,
    target_receives_grass_tile_bonuses,
    unit_can_occupy_tile,
    unit_can_pass_through_units,
    IMPOSSIBLE_MOVEMENT_COST,
)

router = APIRouter(prefix="/games", tags=["games"])
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)


def movement_locked_key(game_link: str, unit_id: int) -> str:
    return f"movement_locked:{game_link}:{unit_id}"


def is_movement_locked(game_link: str, unit_id: int) -> bool:
    return bool(redis_client.get(movement_locked_key(game_link, unit_id)))


def set_movement_locked(game_link: str, unit_id: int) -> None:
    redis_client.set(movement_locked_key(game_link, unit_id), "1")


def clear_movement_locked(game_link: str, unit_id: int) -> None:
    redis_client.delete(movement_locked_key(game_link, unit_id))


def publish_game_ws_event(game_link: str, payload: dict) -> None:
    try:
        redis_client.publish(f"game_updates:{game_link}", json.dumps(payload))
    except Exception:
        # Logging failures should not block game actions.
        return


def append_replay_log_event(game_state: GameState | None, payload: dict) -> None:
    if game_state is None:
        return

    replay = list(game_state.replay_log or [])
    replay.append(payload)

    # Keep replay payload bounded so game responses remain manageable.
    if len(replay) > 500:
        replay = replay[-500:]

    game_state.replay_log = replay


def publish_chat_message_event(
    game_link: str,
    player_id: int,
    username: str,
    message: str,
    game_state: GameState | None = None,
    db: Session | None = None,
) -> None:
    payload = {
        "event": "chat_message",
        "player_id": int(player_id),
        "username": str(username),
        "message": str(message),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    append_replay_log_event(game_state, payload)
    if game_state is not None and db is not None:
        db.add(game_state)
    publish_game_ws_event(game_link, payload)


def publish_system_log_event(
    game_link: str,
    message: str,
    game_state: GameState | None = None,
    db: Session | None = None,
) -> None:
    payload = {
        "event": "system_log",
        "message": str(message),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    append_replay_log_event(game_state, payload)
    if game_state is not None and db is not None:
        db.add(game_state)
    publish_game_ws_event(game_link, payload)


def publish_turn_remaining_warning_if_needed(
    game: Game,
    state: GameState,
    db: Session,
    now: datetime,
) -> bool:
    if state.status != GameStatus.in_progress or not state.turn_deadline:
        return False

    players = list(state.players or [])
    if not players or state.current_turn is None:
        return False

    warning_seconds = 30 if int(game.turn_seconds or 0) <= 60 else 60
    remaining_seconds = int((state.turn_deadline - now).total_seconds())
    if remaining_seconds > warning_seconds or remaining_seconds <= 0:
        return False

    current_turn_index = int(state.current_turn)
    current_player_id = int(players[current_turn_index % len(players)])

    def _as_int(value: object, default: int = -1) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    replay = list(state.replay_log or [])
    for row in reversed(replay):
        if not isinstance(row, dict):
            continue
        if row.get("event") != "system_log":
            continue
        if row.get("warning_type") != "turn_remaining":
            continue
        if _as_int(row.get("turn_index")) != current_turn_index:
            continue
        if _as_int(row.get("warning_seconds")) != warning_seconds:
            continue
        if _as_int(row.get("player_id")) != current_player_id:
            continue
        return False

    current_player_name = get_username_by_id(current_player_id, db)
    payload = {
        "event": "system_log",
        "message": f"{current_player_name} has {warning_seconds} seconds remaining...",
        "created_at": now.isoformat(),
        "warning_type": "turn_remaining",
        "turn_index": current_turn_index,
        "warning_seconds": warning_seconds,
        "player_id": current_player_id,
    }
    append_replay_log_event(state, payload)
    db.add(state)
    publish_game_ws_event(game.link, payload)
    return True


def get_username_by_id(user_id: int, db: Session) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.username:
        return str(user.username)
    return f"Player {user_id}"


def get_unit_display_name(unit: GameUnit, db: Session) -> str:
    owner_name = get_username_by_id(int(unit.user_id or 0), db)

    if getattr(unit, "unit", None) is not None and getattr(unit.unit, "name", None):
        return f"{owner_name}'s {str(unit.unit.name)}"

    unit_meta = db.query(Unit).filter(Unit.id == unit.unit_id).first()
    if unit_meta and unit_meta.name:
        return f"{owner_name}'s {str(unit_meta.name)}"
    return f"{owner_name}'s Unit {unit.id}"


def publish_turn_start_logs(game: Game, state: GameState, db: Session) -> None:
    if state.current_turn is None:
        return

    players = list(state.players or [])
    if not players:
        return

    current_turn_index = int(state.current_turn)
    players_count = len(players)
    is_round_start = (current_turn_index % players_count) == 0
    if is_round_start:
        round_number = (current_turn_index // players_count) + 1
        publish_system_log_event(game.link, f"Turn {round_number}", state, db)

    current_player_id = players[current_turn_index % players_count]
    current_player_name = get_username_by_id(int(current_player_id), db)
    snapshot_turn_stat_stages(int(current_player_id), game.id, db)
    publish_system_log_event(game.link, f"{current_player_name}'s turn", state, db)

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

VALID_STATUS_EFFECTS = {
    "burn",
    "sleep",
    "poison",
    "badly_poisoned",
    "frozen",
    "paralysis",
}

SHORT_DURATION_STATUS_EFFECTS = {"sleep", "frozen"}
# Duration (in turns) for screen-like effects: Reflect, Light Screen, Aurora Veil
SCREEN_EFFECT_DURATION = 5
SIDE_SCREEN_STATE_NAMES = frozenset(
    {"reflect", "light_screen", "aurora_veil", "safeguard", "tailwind"}
)
VALID_STATE_EFFECTS = {"confusion", "flinch", "reflect", "light_screen", "aurora_veil", "safeguard", "tailwind", "aqua_ring", "destiny_bond", "ingrain", "laser_focus", "encore", "heal_block", "cursed", "nightmare", "immobilized", "salt_cure", "taunt", "torment", "telekinesis", "tar_shot", "gastro_acid", "foresight", "mind_reader", "power_trick", "embargo", "glaive_rush", "substitute"}

HELD_ITEM_MASK_TYPE_MAP = {
    "hearthflame_mask": "Fire",
    "wellspring_mask": "Water",
    "cornerstone_mask": "Rock",
}

STATUS_NAME_ALIASES = {
    "badly_poison": "badly_poisoned",
    "badly_poisoned": "badly_poisoned",
}

STAT_LOG_LABELS = {
    "attack": "attack",
    "defense": "defense",
    "sp_attack": "special attack",
    "sp_defense": "special defense",
    "speed": "speed",
    "accuracy": "accuracy",
    "evasion": "evasion",
    "crit": "critical hit rate",
}

STATUS_LOG_LABELS = {
    "burn": "burned",
    "sleep": "asleep",
    "poison": "poisoned",
    "badly_poisoned": "badly poisoned",
    "frozen": "frozen",
    "paralysis": "paralyzed",
}

STATUS_TYPE_IMMUNITIES = {
    "paralysis": {"electric"},
    "poison": {"poison", "steel"},
    "badly_poisoned": {"poison", "steel"},
    "burn": {"fire"},
    "frozen": {"ice"},
}

WEATHER_TO_ID = {
    "sun": 1,
    "rain": 2,
    "sandstorm": 3,
    "hail": 4,
}

FIELD_HAZARD_TO_ID = {
    "spikes": 1,
    "toxic_spikes": 2,
    "stealth_rock": 3,
    "sticky_web": 4,
}

FIELD_HAZARD_STACK_LIMITS = {
    1: 3,  # spikes
    2: 2,  # toxic spikes
    3: 1,  # stealth rock
    4: 1,  # sticky web
}

FIELD_HAZARD_DEFAULT_DURATION = 5

TERRAIN_TO_ID = {
    "electric": 1,
    "psychic": 2,
    "grassy": 3,
    "misty": 4,
}
TERRAIN_ID_TO_NAME = {value: key for key, value in TERRAIN_TO_ID.items()}
TERRAIN_DEFAULT_DURATION = 5

FIELD_EFFECT_TO_ID = {
    "gravity": 1,
}

HIDDEN_ABILITY_COST = 250


def get_unit_flags(unit: GameUnit) -> dict:
    raw = getattr(unit, "flags", None)
    return dict(raw) if isinstance(raw, dict) else {}


def set_unit_flags(unit: GameUnit, flags: dict, db: Session) -> None:
    unit.flags = dict(flags)
    db.add(unit)


def get_unit_held_item(unit: GameUnit) -> str | None:
    item = get_unit_flags(unit).get("held_item")
    if item is None:
        return None
    item_str = str(item).strip()
    return item_str or None


def get_unit_ability_id(unit: GameUnit) -> int | None:
    ability_id = get_unit_flags(unit).get("ability_id")
    if ability_id is not None:
        try:
            return int(ability_id)
        except (TypeError, ValueError):
            pass
    unit_info = getattr(unit, "unit", None)
    if unit_info and isinstance(unit_info.ability_ids, list) and unit_info.ability_ids:
        return int(unit_info.ability_ids[0])
    return None


def set_unit_ability_id(unit: GameUnit, ability_id: int | None, db: Session) -> None:
    flags = get_unit_flags(unit)
    if ability_id is None:
        flags.pop("ability_id", None)
    else:
        flags["ability_id"] = int(ability_id)
    set_unit_flags(unit, flags, db)


def resolve_ability_name(ability_id: int | None, db: Session) -> str | None:
    if ability_id is None:
        return None
    ability = db.query(Ability).filter(Ability.id == ability_id).first()
    return ability.name if ability else None


def is_hidden_ability_for_unit(unit_info: Unit, ability_id: int | None) -> bool:
    if ability_id is None or unit_info.hidden_ability is None:
        return False
    return int(unit_info.hidden_ability) == int(ability_id)


def unit_can_learn_ability(unit_info: Unit, ability_id: int) -> bool:
    allowed = {int(a) for a in (unit_info.ability_ids or [])}
    if unit_info.hidden_ability is not None:
        allowed.add(int(unit_info.hidden_ability))
    return int(ability_id) in allowed


def ability_change_net_cost(
    unit_info: Unit,
    current_ability_id: int | None,
    new_ability_id: int,
) -> int:
    current_hidden = is_hidden_ability_for_unit(unit_info, current_ability_id)
    new_hidden = is_hidden_ability_for_unit(unit_info, new_ability_id)
    if new_hidden and not current_hidden:
        return HIDDEN_ABILITY_COST
    if current_hidden and not new_hidden:
        return -HIDDEN_ABILITY_COST
    return 0


def resolve_held_item_name(item_ref: str | None, db: Session) -> str | None:
    if not item_ref:
        return None
    ref = str(item_ref).strip()
    if not ref:
        return None
    item = db.query(Item).filter((Item.slug == ref) | (Item.name == ref)).first()
    if item:
        return item.name
    return ref.replace("_", " ").title()


def resolve_item_record(item_ref: str | None, db: Session) -> Item | None:
    if not item_ref:
        return None
    ref = str(item_ref).strip()
    if not ref:
        return None
    return db.query(Item).filter((Item.slug == ref) | (Item.name == ref)).first()


def get_held_tm_item(unit: GameUnit, db: Session) -> Item | None:
    item = resolve_item_record(get_unit_held_item(unit), db)
    if not item or item.category != "tm" or not item.move_id:
        return None
    return item


def get_held_tm_move_id(unit: GameUnit, db: Session) -> int | None:
    item = get_held_tm_item(unit, db)
    if not item:
        return None
    return int(item.move_id)


def get_unit_learnset_move_ids(unit_info: Unit) -> set[int]:
    move_ids: set[int] = set()
    for entry in unit_info.level_up_moves or []:
        if isinstance(entry, dict):
            move_id = entry.get("move_id")
            if move_id is not None:
                move_ids.add(int(move_id))
    for move_id in unit_info.tm_moves or []:
        move_ids.add(int(move_id))
    for move_id in unit_info.egg_moves or []:
        move_ids.add(int(move_id))
    return move_ids


def get_default_equipped_move_ids(unit_info: Unit, level: int = 50) -> list[int]:
    return [int(move_id) for move_id in (unit_info.equipped_moves or [])]


def get_unit_equipped_move_ids(unit: GameUnit, unit_info: Unit) -> list[int]:
    flags = get_unit_flags(unit)
    stored = flags.get("move_ids")
    if isinstance(stored, list) and stored:
        return [int(move_id) for move_id in stored]
    return get_default_equipped_move_ids(unit_info, unit.level or 50)


def unit_knows_move(unit_info: Unit, move_id: int, unit: GameUnit, db: Session) -> bool:
    equipped_move_ids = get_unit_equipped_move_ids(unit, unit_info)
    if move_id in equipped_move_ids:
        return True
    tm_move_id = get_held_tm_move_id(unit, db)
    if tm_move_id == move_id:
        tm_moves = {int(mid) for mid in (unit_info.tm_moves or [])}
        return move_id in tm_moves
    return False


def resolve_move_pp_index(unit: GameUnit, unit_info: Unit, move_id: int, db: Session) -> int | None:
    equipped_move_ids = get_unit_equipped_move_ids(unit, unit_info)
    if move_id in equipped_move_ids:
        return equipped_move_ids.index(move_id)
    tm_move_id = get_held_tm_move_id(unit, db)
    if tm_move_id == move_id:
        return len(equipped_move_ids)
    return None


def sync_tm_move_pp(unit: GameUnit, unit_info: Unit, db: Session) -> None:
    base_move_ids = get_unit_equipped_move_ids(unit, unit_info)
    tm_move_id = get_held_tm_move_id(unit, db)
    has_extra_tm = tm_move_id is not None and tm_move_id not in base_move_ids
    expected_len = len(base_move_ids) + (1 if has_extra_tm else 0)

    pp_list = list(unit.move_pp) if isinstance(unit.move_pp, list) else []

    while len(pp_list) < len(base_move_ids):
        move = db.query(Move).filter_by(id=base_move_ids[len(pp_list)]).first()
        pp_list.append(move.pp if move and move.pp is not None else 0)

    if has_extra_tm:
        if len(pp_list) < expected_len:
            tm_move = db.query(Move).filter_by(id=tm_move_id).first()
            pp_list.append(tm_move.pp if tm_move and tm_move.pp is not None else 0)
    elif len(pp_list) > len(base_move_ids):
        pp_list = pp_list[: len(base_move_ids)]

    unit.move_pp = pp_list
    db.add(unit)


def preparation_item_allowed(item: Item, game: Game) -> bool:
    if item.category == "tm" and not game.start_with_tms:
        return False
    return True


def attach_game_unit_loadout_fields(unit: GameUnit, db: Session) -> GameUnit:
    slug = get_unit_held_item(unit)
    unit.held_item_slug = slug
    unit.held_item = resolve_held_item_name(slug, db)
    unit.held_tm_move_id = get_held_tm_move_id(unit, db)
    unit.ability_id = get_unit_ability_id(unit)
    unit.ability = resolve_ability_name(unit.ability_id, db)
    if unit.unit:
        unit.equipped_move_ids = get_unit_equipped_move_ids(unit, unit.unit)
    else:
        unit.equipped_move_ids = []
    return unit


def unit_holds_item_type(unit: GameUnit, item_type: str) -> bool:
    item = get_unit_held_item(unit)
    if not item:
        return False
    return item_type.lower() in item.lower()


def set_unit_held_item(unit: GameUnit, item: str | None, db: Session) -> None:
    flags = get_unit_flags(unit)
    if item:
        flags["held_item"] = str(item)
    else:
        flags.pop("held_item", None)
    set_unit_flags(unit, flags, db)


def remove_unit_held_item(unit: GameUnit, db: Session) -> bool:
    if not get_unit_held_item(unit):
        return False
    set_unit_held_item(unit, None, db)
    return True


def consume_unit_held_item(unit: GameUnit, db: Session, *, item_type: str | None = None) -> bool:
    item = get_unit_held_item(unit)
    if not item:
        return False
    if item_type and item_type.lower() not in item.lower():
        return False
    if is_item_suppressed(unit):
        return False
    set_unit_held_item(unit, None, db)
    return True


def unit_has_positive_stat_stage(unit: GameUnit) -> bool:
    for stat in ALL_STAT_EFFECT_KEYS:
        if get_stat_stage(unit.stat_boosts, stat) > 0:
            return True
    return False


def snapshot_turn_stat_stages(user_id: int, game_id: int, db: Session) -> None:
    units = db.query(GameUnit).filter(GameUnit.game_id == game_id, GameUnit.user_id == user_id).all()
    for unit in units:
        flags = get_unit_flags(unit)
        flags["stat_stages_at_turn_start"] = {
            stat: get_stat_stage(unit.stat_boosts, stat) for stat in ALL_STAT_EFFECT_KEYS
        }
        flags["allies_defeated_since_turn"] = 0
        set_unit_flags(unit, flags, db)


def unit_stats_lowered_since_turn_start(unit: GameUnit) -> bool:
    snapshot = get_unit_flags(unit).get("stat_stages_at_turn_start")
    if not isinstance(snapshot, dict):
        return False
    for stat in ALL_STAT_EFFECT_KEYS:
        previous = int(snapshot.get(stat, 0) or 0)
        current = get_stat_stage(unit.stat_boosts, stat)
        if current < previous:
            return True
    return False


def unit_stats_raised_since_turn_start(unit: GameUnit) -> bool:
    snapshot = get_unit_flags(unit).get("stat_stages_at_turn_start")
    if not isinstance(snapshot, dict):
        return False
    for stat in ALL_STAT_EFFECT_KEYS:
        previous = int(snapshot.get(stat, 0) or 0)
        current = get_stat_stage(unit.stat_boosts, stat)
        if current > previous:
            return True
    return False


def record_last_damage_received(target: GameUnit, attacker: GameUnit, damage: int, db: Session) -> None:
    if damage <= 0:
        return
    flags = get_unit_flags(target)
    flags["last_damage_attacker_id"] = int(attacker.id)
    flags["last_damage_amount"] = int(damage)
    flags["times_hit"] = int(flags.get("times_hit", 0) or 0) + 1
    set_unit_flags(target, flags, db)


def increment_allies_defeated_since_turn(fainted_unit: GameUnit, db: Session) -> None:
    game_id = getattr(fainted_unit, "game_id", None)
    user_id = getattr(fainted_unit, "user_id", None)
    if not isinstance(game_id, int) or not isinstance(user_id, int):
        return
    allies = (
        db.query(GameUnit)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.user_id == user_id,
            GameUnit.is_fainted == False,
            GameUnit.current_hp > 0,
        )
        .all()
    )
    for ally in allies:
        flags = get_unit_flags(ally)
        flags["allies_defeated_since_turn"] = int(flags.get("allies_defeated_since_turn", 0) or 0) + 1
        set_unit_flags(ally, flags, db)


def unit_has_glaive_rush(unit: GameUnit) -> bool:
    state = normalize_states(unit.states)
    return bool(state and str(state[0]).lower() == "glaive_rush" and int(state[1]) > 0)


def move_has_revive_effect(move: Move) -> bool:
    if not move or not isinstance(move.effects, list):
        return False
    for effect in move.effects:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) >= 2 and parts[0] == "target" and parts[1] == "revive":
            return True
    return False


def move_ignores_target_stat_changes(move: Move) -> bool:
    return move_has_effect_token(move, "target:ignore_stat_changes")


def move_ignores_fairy_immunity(move: Move) -> bool:
    return move_has_effect_token(move, "self:ignore_fairy_immunity")


def get_unboosted_battle_stat(unit: GameUnit, stat: str, db: Session) -> int:
    stat = normalize_stat_name(stat)
    effective = compute_effective_stats(unit, db)
    boosted_value = int(effective.get(stat, 0) or 0)
    if boosted_value <= 0:
        return boosted_value
    stage_multiplier = get_stat_multiplier(unit.stat_boosts, stat)
    if stage_multiplier <= 0:
        return boosted_value
    return max(1, int(boosted_value / stage_multiplier))


def resolve_move_type_from_held_item(attacker: GameUnit, item_category: str) -> str | None:
    held_item = str(get_unit_held_item(attacker) or "").lower()
    if not held_item:
        return None
    category = str(item_category or "").lower()
    if category == "mask":
        for slug, move_type in HELD_ITEM_MASK_TYPE_MAP.items():
            if slug in held_item:
                return move_type
    return None


def resolve_power_add(move: Move, attacker: GameUnit) -> int:
    bonus = 0
    if not move or not isinstance(move.effects, list):
        return bonus

    base_power = int(move.power or 0)
    flags = get_unit_flags(attacker)

    for effect in move.effects:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) < 3 or parts[0] != "power_add":
            continue

        try:
            per_unit = int(parts[2])
        except ValueError:
            continue

        if parts[1] == "times_hit":
            hits = int(flags.get("times_hit", 0) or 0)
            bonus += hits * per_unit
            if len(parts) >= 4:
                try:
                    power_cap = int(parts[3])
                    bonus = min(bonus, max(0, power_cap - base_power))
                except ValueError:
                    pass
        elif parts[1] == "allies_defeated_since_turn":
            defeated = int(flags.get("allies_defeated_since_turn", 0) or 0)
            bonus += defeated * per_unit

    return max(0, bonus)


def resolve_weather_move_multiplier_for_move(
    move: Move,
    move_type: str | None,
    weather_id: int,
) -> float:
    if move and isinstance(move.effects, list):
        for effect in move.effects:
            parts = str(effect or "").strip().lower().split(":")
            if len(parts) >= 4 and parts[0] == "weather_override" and weather_condition_matches(weather_id, parts[1]):
                try:
                    return float(parts[2])
                except ValueError:
                    continue
    return get_weather_move_multiplier(move_type, weather_id)


def faint_unit_in_place(unit: GameUnit, db: Session) -> None:
    unit.is_fainted = True
    unit.current_hp = 0
    unit.can_move = False
    unit.current_x = -1
    unit.current_y = -1
    increment_allies_defeated_since_turn(unit, db)
    db.add(unit)


def normalize_timed_tile_cell(cell) -> list[int]:
    if isinstance(cell, list):
        if len(cell) >= 2:
            try:
                effect_id = int(cell[0] or 0)
                turns = int(cell[1] or 0)
                if effect_id > 0 and turns > 0:
                    return [effect_id, turns]
            except (TypeError, ValueError):
                pass
        if len(cell) == 1:
            try:
                effect_id = int(cell[0] or 0)
                if effect_id > 0:
                    return [effect_id, TERRAIN_DEFAULT_DURATION]
            except (TypeError, ValueError):
                pass
    try:
        effect_id = int(cell or 0)
        if effect_id > 0:
            return [effect_id, TERRAIN_DEFAULT_DURATION]
    except (TypeError, ValueError):
        pass
    return [0, 0]


def get_timed_effect_id_at_position(tiles: list | None, x: int, y: int) -> int:
    if not isinstance(tiles, list) or y < 0 or x < 0 or y >= len(tiles):
        return 0
    row = tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return 0
    cell = normalize_timed_tile_cell(row[x])
    return int(cell[0] or 0)


def get_terrain_id_at_position(terrain_tiles: list | None, x: int, y: int) -> int:
    return get_timed_effect_id_at_position(terrain_tiles, x, y)


def get_unit_terrain_id(unit: GameUnit, terrain_tiles: list | None) -> int:
    x = int(getattr(unit, "current_x", -1) or -1)
    y = int(getattr(unit, "current_y", -1) or -1)
    return get_terrain_id_at_position(terrain_tiles, x, y)


def terrain_condition_matches(terrain_id: int, condition: str) -> bool:
    condition_lower = str(condition or "").lower()
    if condition_lower in {"", "*", "any"}:
        return terrain_id > 0
    if condition_lower == "none":
        return terrain_id == 0
    expected = TERRAIN_TO_ID.get(condition_lower)
    return expected is not None and terrain_id == expected


def get_field_effect_at_position(field_effect_tiles: list | None, x: int, y: int) -> int:
    if not isinstance(field_effect_tiles, list) or y < 0 or x < 0 or y >= len(field_effect_tiles):
        return 0
    row = field_effect_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return 0
    try:
        return int(row[x] or 0)
    except (TypeError, ValueError):
        return 0


def is_gravity_active_at(unit: GameUnit, field_effect_tiles: list | None) -> bool:
    x = int(getattr(unit, "current_x", -1) or -1)
    y = int(getattr(unit, "current_y", -1) or -1)
    gravity_id = FIELD_EFFECT_TO_ID.get("gravity", 0)
    return gravity_id > 0 and get_field_effect_at_position(field_effect_tiles, x, y) == gravity_id


def move_has_effect_token(move: Move, token: str) -> bool:
    if not move or not isinstance(move.effects, list):
        return False
    target = str(token or "").strip().lower()
    for effect in move.effects:
        if str(effect or "").strip().lower() == target:
            return True
    return False


def resolve_move_type_for_execution(
    move: Move,
    attacker: GameUnit,
    terrain_tiles: list | None,
    db: Session | None = None,
) -> str:
    move_type = str(move.type or "Normal")
    if move_has_effect_token(move, "self:modify_move_type_by_terrain"):
        terrain_id = get_unit_terrain_id(attacker, terrain_tiles)
        mapped = TERRAIN_ID_TO_NAME.get(terrain_id)
        type_map = {
            "electric": "Electric",
            "psychic": "Psychic",
            "grassy": "Grass",
            "misty": "Fairy",
        }
        if mapped in type_map:
            return type_map[mapped]

    for effect in move.effects or []:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) >= 3 and parts[0] == "self" and parts[1] == "modify_move_type_by_held_item":
            mapped_type = resolve_move_type_from_held_item(attacker, parts[2])
            if mapped_type:
                return mapped_type

    return move_type


def resolve_power_multiplier(
    move: Move,
    attacker: GameUnit,
    target: GameUnit | None,
    terrain_tiles: list | None,
    field_effect_tiles: list | None,
    db: Session,
    *,
    weather_tiles: list | None = None,
) -> float:
    multiplier = 1.0
    if not move or not isinstance(move.effects, list):
        return multiplier

    attacker_terrain = get_unit_terrain_id(attacker, terrain_tiles)
    target_terrain = get_unit_terrain_id(target, terrain_tiles) if target is not None else 0

    for effect in move.effects:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) < 2 or parts[0] != "conditional_power":
            continue

        if len(parts) >= 4 and parts[1] == "terrain":
            terrain_name = parts[2]
            try:
                factor = float(parts[3])
            except ValueError:
                continue
            if terrain_condition_matches(attacker_terrain, terrain_name):
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "target_terrain":
            terrain_name = parts[2]
            try:
                factor = float(parts[3])
            except ValueError:
                continue
            if target is not None and terrain_condition_matches(target_terrain, terrain_name):
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "field" and parts[2] == "gravity":
            try:
                factor = float(parts[3])
            except ValueError:
                continue
            if target is not None and is_gravity_active_at(target, field_effect_tiles):
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "self" and parts[2] == "stat_lowered_since_turn":
            try:
                factor = float(parts[3])
            except ValueError:
                continue
            if unit_stats_lowered_since_turn_start(attacker):
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "target_status":
            if target is None:
                continue
            status_name = parts[2]
            try:
                factor = float(parts[3])
            except ValueError:
                continue
            current_status = normalize_status_effects(target.status_effects)
            if current_status and str(current_status[0]).lower() == status_name:
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "target" and parts[2] == "has_status":
            try:
                factor = float(parts[3])
            except ValueError:
                continue
            if target is not None and unit_has_status_condition(target):
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "super_effective":
            if target is None:
                continue
            move_type = str(move.type or "Normal")
            target_types = list(getattr(target.unit, "types", None) or [])
            if not target_types:
                target_types = list(get_unit_types(target, db))
            type_multiplier = get_type_multiplier(move_type, (target_types, target, db))
            try:
                factor = float(parts[2])
            except ValueError:
                continue
            if type_multiplier > 1.0:
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "chance":
            try:
                chance = int(parts[2])
                factor = float(parts[3])
            except ValueError:
                continue
            if random.randint(1, 100) <= chance:
                multiplier *= factor
        elif len(parts) >= 4 and parts[1] == "weather":
            weather_name = parts[2]
            try:
                factor = float(parts[3])
            except ValueError:
                continue
            attacker_weather_id = get_unit_weather_id(attacker, weather_tiles)
            if weather_condition_matches(attacker_weather_id, weather_name):
                multiplier *= factor

    return multiplier


def unit_has_status_condition(unit: GameUnit) -> bool:
    current_status = normalize_status_effects(unit.status_effects)
    return bool(current_status) and int(current_status[1] or 0) > 0


def resolve_move_accuracy(
    move: Move,
    target: GameUnit,
    weather_tiles: list | None,
) -> int | None:
    if move.accuracy is None:
        return None

    accuracy = int(move.accuracy)
    for effect in move.effects or []:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) >= 4 and parts[0] == "conditional_accuracy" and parts[1] == "weather":
            weather_name = parts[2]
            try:
                override = int(parts[3])
            except ValueError:
                continue
            target_weather_id = get_unit_weather_id(target, weather_tiles)
            if weather_condition_matches(target_weather_id, weather_name):
                accuracy = override

    return accuracy


def get_scaling_hit_powers(move: Move) -> list[int] | None:
    if not move or not isinstance(move.effects, list):
        return None
    for effect in move.effects:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) >= 3 and parts[0] == "multi_hit" and parts[1] == "scaling":
            powers: list[int] = []
            for token in parts[2].split(","):
                try:
                    powers.append(int(token))
                except ValueError:
                    continue
            return powers or None
    return None


def move_uses_separate_hit_accuracy(move: Move) -> bool:
    if not move or not isinstance(move.effects, list):
        return False
    for effect in move.effects:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) >= 4 and parts[0] == "multi_hit" and parts[1] == "scaling" and parts[3] == "separate_accuracy":
            return True
    return False


def get_move_hit_count(move: Move, *, landed_target_count: int = 1) -> int:
    """Resolve how many times a move should hit from its multi_hit effect token."""
    if not move or not isinstance(move.effects, list):
        return 1

    for effect in move.effects:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) < 2 or parts[0] != "multi_hit":
            continue

        hit_mode = parts[1]
        if hit_mode == "dragon_darts":
            return 2 if landed_target_count == 1 else 1
        if hit_mode == "scaling":
            powers = get_scaling_hit_powers(move)
            return len(powers) if powers else 1

        if hit_mode == "variable":
            roll = random.randint(1, 20)
            if roll <= 7:
                return 2
            if roll <= 14:
                return 3
            if roll <= 17:
                return 4
            return 5

        if hit_mode == "party":
            return 1

        try:
            minimum_hits = max(1, int(hit_mode))
        except ValueError:
            return 1

        maximum_hits = minimum_hits
        if len(parts) >= 3:
            try:
                maximum_hits = max(minimum_hits, int(parts[2]))
            except ValueError:
                maximum_hits = minimum_hits

        if minimum_hits == maximum_hits:
            return minimum_hits
        return random.randint(minimum_hits, maximum_hits)

    return 1


def move_requires_target_held_item(move: Move) -> bool:
    return move_has_effect_token(move, "requires:target:held_item")


def move_requires_attacker_berry(move: Move) -> bool:
    return move_has_effect_token(move, "requires:held_item:berry")


def move_requires_target_terrain(move: Move) -> bool:
    return move_has_effect_token(move, "requires:target_terrain:active")


def move_ignores_redirect(move: Move) -> bool:
    return move_has_effect_token(move, "ignore_redirect")


def move_uses_best_offense(move: Move) -> bool:
    return move_has_effect_token(move, "self:use_best_offense")


def validate_move_execution(
    move: Move,
    attacker: GameUnit,
    targets: List[GameUnit],
    terrain_tiles: list | None,
    db: Session,
) -> str | None:
    if move_requires_attacker_berry(move) and not unit_holds_item_type(attacker, "berry"):
        return "It doesn't have a Berry to eat"

    if move_requires_target_held_item(move):
        if not targets:
            return "The move failed"
        if any(not get_unit_held_item(target) for target in targets):
            return "The move failed because the target has no item"

    if move_requires_target_terrain(move):
        if not targets:
            return "But it failed"
        if any(get_unit_terrain_id(target, terrain_tiles) <= 0 for target in targets):
            return "But it failed"

    attacker_types = get_unit_types(attacker, db)
    for effect in move.effects or []:
        parts = str(effect or "").strip().lower().split(":")
        if len(parts) >= 3 and parts[0] == "requires" and parts[1] == "type":
            required_type = parts[2]
            if required_type not in attacker_types:
                return "But it failed"
        if str(effect or "").strip().lower() == "requires:last_damage_attacker":
            flags = get_unit_flags(attacker)
            last_attacker_id = flags.get("last_damage_attacker_id")
            if last_attacker_id is None:
                return "But it failed"
            try:
                last_attacker_id = int(last_attacker_id)
            except (TypeError, ValueError):
                return "But it failed"
            last_attacker = db.query(GameUnit).filter(GameUnit.id == last_attacker_id).first()
            if last_attacker is None or int(last_attacker.current_hp or 0) <= 0:
                return "But it failed"
        if len(parts) >= 2 and parts[0] == "fail_if":
            if parts[1] == "below_half_hp":
                max_hp = int((attacker.current_stats or {}).get("hp", attacker.current_hp or 0) or 0)
                if max_hp > 0 and int(attacker.current_hp or 0) < (max_hp // 2):
                    return "But it failed"
            elif parts[1] == "stats_at_max" and len(parts) >= 3:
                stat_names = [normalize_stat_name(token) for token in parts[2].split(",") if token.strip()]
                if stat_names and all(get_stat_stage(attacker.stat_boosts, stat) >= 6 for stat in stat_names):
                    return "But it failed"
        if move_has_revive_effect(move):
            att_state = normalize_states(attacker.states)
            if att_state and att_state[0] == "heal_block" and int(att_state[1]) > 0:
                return "But it failed"

    return None


def clear_terrain_at_position(map_state: "GameMapState", x: int, y: int, db: Session) -> None:
    if map_state is None or not isinstance(map_state.terrain_effect_tiles, list):
        return
    if y < 0 or x < 0 or y >= len(map_state.terrain_effect_tiles):
        return
    row = map_state.terrain_effect_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return
    row[x] = [0, 0]
    db.add(map_state)


def estimate_damage_for_mode(
    *,
    power: int,
    level: int,
    attack: float,
    defense: float,
    stab: float,
    type_multiplier: float,
    weather_move_multiplier: float,
    targets_multiplier: float,
) -> float:
    safe_defense = defense if defense > 0 else 1
    base = (((2 * level) / 5 + 2) * power * (attack / safe_defense)) / 50 + 2
    return base * targets_multiplier * stab * type_multiplier * weather_move_multiplier


def resolve_shell_side_arm_mode(
    move: Move,
    attacker: GameUnit,
    target: GameUnit,
    *,
    terrain_tiles: list | None,
    weather_tiles: list | None,
    special_tiles: list | None,
    db: Session,
    targets_multiplier: float,
) -> tuple[bool, bool]:
    """Return (is_special, makes_contact) for Shell Side Arm."""
    move_type = str(move.type or "Poison")
    attacker_types = getattr(attacker.unit, "types", None) or []
    stab = 1.5 if move_type in attacker_types else 1
    attacker_weather_id = get_unit_weather_id(attacker, weather_tiles)
    weather_move_multiplier = get_weather_move_multiplier(move_type, attacker_weather_id)
    type_multiplier = get_type_multiplier(move_type, (getattr(target.unit, "types", None) or [], target, db))
    power = move.power or 0
    level = attacker.level or 50

    target_weather_id = get_unit_weather_id(target, weather_tiles)
    target_types = get_unit_types(target, db)
    target_ability_names = get_unit_ability_names(target, db)

    physical_attack = (attacker.current_stats or {}).get("attack", 0) or 0
    physical_defense = (target.current_stats or {}).get("defense", 1) or 1
    physical_defense *= get_weather_defense_multiplier(target, "defense", target_weather_id, db)
    physical_defense *= get_tile_defense_multiplier(
        special_tiles,
        int(target.current_x),
        int(target.current_y),
        target_types,
        target_ability_names,
    )
    physical_estimate = estimate_damage_for_mode(
        power=power,
        level=level,
        attack=physical_attack,
        defense=physical_defense,
        stab=stab,
        type_multiplier=type_multiplier,
        weather_move_multiplier=weather_move_multiplier,
        targets_multiplier=targets_multiplier,
    )

    special_attack = (attacker.current_stats or {}).get("sp_attack", 0) or 0
    special_defense = (target.current_stats or {}).get("sp_defense", 1) or 1
    special_defense *= get_weather_defense_multiplier(target, "sp_defense", target_weather_id, db)
    special_defense *= get_tile_defense_multiplier(
        special_tiles,
        int(target.current_x),
        int(target.current_y),
        target_types,
        target_ability_names,
    )
    special_estimate = estimate_damage_for_mode(
        power=power,
        level=level,
        attack=special_attack,
        defense=special_defense,
        stab=stab,
        type_multiplier=type_multiplier,
        weather_move_multiplier=weather_move_multiplier,
        targets_multiplier=targets_multiplier,
    )

    if physical_estimate >= special_estimate:
        return False, True
    return True, False


def normalize_hazard_cell(cell: list | None) -> list[list[int]]:
    normalized: list[list[int]] = []
    if not isinstance(cell, list):
        return normalized

    for entry in cell:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        try:
            hazard_id = int(entry[0])
            turns_remaining = int(entry[1])
        except (TypeError, ValueError):
            continue

        if hazard_id <= 0 or turns_remaining <= 0:
            continue
        normalized.append([hazard_id, turns_remaining])

    return normalized


def try_add_hazard_stack(hazard_entries: list[list[int]], hazard_id: int, duration_turns: int) -> bool:
    if hazard_id <= 0 or duration_turns <= 0:
        return False

    max_stacks = int(FIELD_HAZARD_STACK_LIMITS.get(hazard_id, 1))
    current_stacks = sum(1 for entry in hazard_entries if int(entry[0]) == hazard_id)
    if current_stacks >= max_stacks:
        return False

    hazard_entries.append([hazard_id, duration_turns])
    return True


def clear_hazards_on_tiles(map_state: "GameMapState", affected_tiles: list[tuple[int, int]], db: Session) -> bool:
    if map_state is None or not isinstance(map_state.hazard_tiles, list):
        return False

    changed = False
    for tx, ty in affected_tiles:
        if ty < 0 or tx < 0 or ty >= len(map_state.hazard_tiles):
            continue
        row = map_state.hazard_tiles[ty]
        if not isinstance(row, list) or tx >= len(row):
            continue
        if normalize_hazard_cell(row[tx]):
            row[tx] = []
            changed = True

    if changed:
        db.add(map_state)
    return changed


def clear_substitutes_on_tiles(
    game_id: int,
    affected_tiles: list[tuple[int, int]],
    db: Session,
    *,
    game: "Game | None" = None,
    game_state: "GameState | None" = None,
) -> bool:
    tile_set = set(affected_tiles)
    if not tile_set:
        return False

    units = db.query(GameUnit).filter(GameUnit.game_id == game_id).all()
    changed = False
    for unit in units:
        if int(unit.current_x) < 0 or int(unit.current_y) < 0:
            continue
        if (int(unit.current_x), int(unit.current_y)) not in tile_set:
            continue
        state = normalize_states(unit.states)
        if state and str(state[0]).lower() == "substitute" and int(state[1]) > 0:
            unit.states = []
            db.add(unit)
            changed = True
            if game and game_state:
                publish_system_log_event(
                    game.link,
                    f"{get_unit_display_name(unit, db)}'s substitute was removed",
                    game_state,
                    db,
                )
    return changed


def find_revival_placement_tile(attacker: GameUnit, map_obj: Map, db: Session, *, pulse: int = 3) -> tuple[int, int] | None:
    width = int(getattr(map_obj, "width", 0) or 0)
    height = int(getattr(map_obj, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return None

    origin_x = int(attacker.current_x)
    origin_y = int(attacker.current_y)
    affected_tiles = get_pulse_tiles_backend(origin_x, origin_y, pulse, width, height)
    occupied = {
        (int(unit.current_x), int(unit.current_y))
        for unit in db.query(GameUnit).filter(
            GameUnit.game_id == attacker.game_id,
            GameUnit.is_fainted == False,
            GameUnit.current_hp > 0,
        ).all()
        if int(unit.current_x) >= 0 and int(unit.current_y) >= 0
    }

    for tile in affected_tiles:
        if tile not in occupied:
            return tile
    return None


def get_weather_id_at_position(weather_tiles: list | None, x: int, y: int) -> int:
    if not isinstance(weather_tiles, list) or y < 0 or x < 0 or y >= len(weather_tiles):
        return 0
    row = weather_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return 0
    try:
        return int(row[x] or 0)
    except (TypeError, ValueError):
        return 0


def get_unit_weather_id(unit: GameUnit, weather_tiles: list | None) -> int:
    x = int(getattr(unit, "current_x", -1) or -1)
    y = int(getattr(unit, "current_y", -1) or -1)
    return get_weather_id_at_position(weather_tiles, x, y)


def get_hazard_entries_at_position(hazard_tiles: list | None, x: int, y: int) -> list[list[int]]:
    if not isinstance(hazard_tiles, list) or y < 0 or x < 0 or y >= len(hazard_tiles):
        return []
    row = hazard_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return []
    return normalize_hazard_cell(row[x])


def get_weather_name_from_id(weather_id: int) -> str:
    """Convert weather ID back to name. ID 0 is 'clear'."""
    for name, wid in WEATHER_TO_ID.items():
        if wid == weather_id:
            return name
    return "clear"


def weather_condition_matches(weather_id: int, condition: str) -> bool:
    """Check if a weather condition matches the current weather_id.
    
    Args:
        weather_id: Current weather ID (0=clear, 1=sun, 2=rain, 3=sandstorm, 4=hail)
        condition: Condition string ('sun', 'clear', '*', etc.)
    
    Returns:
        True if condition matches current weather
    """
    condition_lower = str(condition or "").lower()
    
    # Wildcard always matches
    if condition_lower == "*":
        return True
    
    # Map condition name to ID and compare
    if condition_lower == "clear":
        return weather_id == 0
    
    condition_id = WEATHER_TO_ID.get(condition_lower)
    if condition_id is not None:
        return weather_id == condition_id
    
    return False


def get_weather_move_multiplier(move_type: str | None, attacker_weather_id: int) -> float:
    move_type_norm = str(move_type or "").lower()
    if attacker_weather_id == WEATHER_TO_ID["rain"]:
        if move_type_norm == "water":
            return 1.5
        if move_type_norm == "fire":
            return 0.5
    elif attacker_weather_id == WEATHER_TO_ID["sun"]:
        if move_type_norm == "fire":
            return 1.5
        if move_type_norm == "water":
            return 0.5
    return 1.0


def get_weather_defense_multiplier(target: GameUnit, defense_stat: str, target_weather_id: int, db: Session) -> float:
    target_types = get_unit_types(target, db)

    # Sandstorm boosts Rock-type special bulk.
    if (
        target_weather_id == WEATHER_TO_ID["sandstorm"]
        and defense_stat == "sp_defense"
        and "rock" in target_types
    ):
        return 1.5

    # Hail boosts Ice-type physical bulk.
    if (
        target_weather_id == WEATHER_TO_ID["hail"]
        and defense_stat == "defense"
        and "ice" in target_types
    ):
        return 1.5

    return 1.0


def parse_move_range_spec(move: Move) -> tuple[str, int]:
    raw = str(getattr(move, "range", "") or getattr(move, "targeting", "") or "").lower().strip()
    m = re.match(r"^([a-z_]+)(?::(\d+))?$", raw)
    if not m:
        return "", 0
    kind = m.group(1) or ""
    offset = int(m.group(2)) if m.group(2) else 0
    return kind, offset


def get_pulse_tiles_backend(origin_x: int, origin_y: int, pulse: int, width: int, height: int) -> list[tuple[int, int]]:
    # Must mirror frontend pulse semantics exactly.
    # pulse:1 -> cardinal neighbors at radius 1 (no diagonals)
    # pulse:2 -> radius 1 including diagonals, excluding self
    # pulse:3 -> radius 1 including diagonals and self
    # pulse:4/5/6 are the above, extended to radius 2
    is_extended = pulse >= 4
    radius = 2 if is_extended else 1
    base_mode = ((pulse - 1) % 3) + 1  # maps 1..6 -> 1..3

    tiles: list[tuple[int, int]] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            tx = origin_x + dx
            ty = origin_y + dy
            if tx < 0 or ty < 0 or tx >= width or ty >= height:
                continue

            manhattan = abs(dx) + abs(dy)
            chebyshev = max(abs(dx), abs(dy))

            if base_mode == 1:
                if manhattan >= 1 and manhattan <= radius and (dx == 0 or dy == 0):
                    tiles.append((tx, ty))
            elif base_mode == 2:
                if chebyshev >= 1 and chebyshev <= radius:
                    tiles.append((tx, ty))
            else:
                if chebyshev <= radius:
                    tiles.append((tx, ty))

    return tiles


def get_move_affected_tiles(move: Move, attacker: GameUnit, width: int, height: int) -> list[tuple[int, int]]:
    x = int(getattr(attacker, "current_x", 0) or 0)
    y = int(getattr(attacker, "current_y", 0) or 0)
    kind, offset = parse_move_range_spec(move)

    if kind == "pulse":
        pulse = offset if offset > 0 else 1
        return get_pulse_tiles_backend(x, y, pulse, width, height)

    # Conservative default for field moves that do not yet have backend tile logic:
    # affect only user's tile instead of entire map.
    if 0 <= x < width and 0 <= y < height:
        return [(x, y)]
    return []


def get_type_multiplier(
    move_type: str,
    defender_types: List[str],
    *,
    ignore_fairy_immunity: bool = False,
) -> float:
    # Backwards-compatible signature: accept optional defender unit by passing as third arg
    defender_unit = None
    db = None
    # If caller passed a GameUnit instead of a list for defender_types, adjust
    if not move_type:
        return 1
    # Allow defender_types to be either a list of types or (types, unit, db)
    if isinstance(defender_types, tuple) and len(defender_types) >= 2:
        # Expect (types_list, defender_unit) or (types_list, defender_unit, db)
        types_list = defender_types[0]
        defender_unit = defender_types[1] if len(defender_types) >= 2 else None
        db = defender_types[2] if len(defender_types) >= 3 else None
        defender_types = types_list

    chart = TYPE_EFFECTIVENESS.get(str(move_type).lower())
    if not chart:
        return 1
    multiplier = 1.0
    for dtype in defender_types or []:
        key = str(dtype).lower()
        # Handle immunities; certain states (foresight/mind_reader) can bypass them
        if key in chart.get("immune", []):
            if ignore_fairy_immunity and key == "fairy" and str(move_type).lower() == "dragon":
                pass
            else:
                try:
                    # If defender_unit supplied and has foresight/mind_reader, ignore specific immunities
                    if defender_unit is not None:
                        s = normalize_states(defender_unit.states)
                        if s and int(s[1]) > 0:
                            state_name = s[0]
                            if state_name == "foresight" and str(move_type).lower() in {"normal", "fighting"}:
                                # bypass immunity
                                pass
                            elif state_name == "mind_reader" and str(move_type).lower() == "psychic":
                                pass
                            else:
                                return 0
                        else:
                            return 0
                    else:
                        return 0
                except Exception:
                    return 0
        if key in chart.get("weak", []):
            multiplier *= 2
        elif key in chart.get("resist", []):
            multiplier *= 0.5
    return multiplier

def normalize_stat_name(stat: str) -> str:
    """Normalize stat names to match model field names."""
    mapping = {
        "special_attack": "sp_attack",
        "special_defense": "sp_defense",
        "sp attack": "sp_attack",
        "sp defense": "sp_defense",
    }
    return mapping.get(stat.lower(), stat.lower())


def default_stat_boosts() -> dict:
    return {
        "attack": [],
        "defense": [],
        "sp_attack": [],
        "sp_defense": [],
        "speed": [],
        "accuracy": [],
        "evasion": [],
        "crit": [],
    }


# Omniboost/omnidebuff effects (e.g., Ancient Power) affect battle stats only.
# Range is excluded because it is derived from speed.
ALL_STAT_EFFECT_KEYS = ["attack", "defense", "sp_attack", "sp_defense", "speed"]


def normalize_status_name(status: str) -> str:
    normalized = str(status).lower().strip()
    return STATUS_NAME_ALIASES.get(normalized, normalized)


def format_stat_log_label(stat: str) -> str:
    normalized_stat = normalize_stat_name(stat)
    if normalized_stat == "all":
        return "all stats"
    return STAT_LOG_LABELS.get(normalized_stat, normalized_stat.replace("_", " "))


def format_status_log_label(status: str) -> str:
    normalized_status = normalize_status_name(status)
    return STATUS_LOG_LABELS.get(normalized_status, normalized_status.replace("_", " "))


def format_state_log_message(unit: GameUnit, state_name: str, db: Session) -> str:
    display_name = get_unit_display_name(unit, db)
    normalized_state = str(state_name or "").strip().lower()
    if normalized_state == "flinch":
        return f"{display_name} flinched"
    if normalized_state == "confusion":
        return f"{display_name} is confused"
    return f"{display_name} gained {normalized_state}"


def format_stat_change_outcome_phrase(delta_stage: int, attempted_direction: int) -> str:
    """Format user-facing stat change outcome text from applied stage delta."""
    if delta_stage > 0:
        if delta_stage == 1:
            return "rose."
        if delta_stage == 2:
            return "rose sharply."
        return "rose drastically."

    if delta_stage < 0:
        if delta_stage == -1:
            return "fell."
        if delta_stage == -2:
            return "harshly fell."
        return "severely fell."

    if attempted_direction >= 0:
        return "won't go higher."
    return "won't go lower."


def normalize_status_effects(raw: list | dict | str | None) -> list:
    def parse_single_status(value) -> list | None:
        if isinstance(value, dict):
            status = normalize_status_name(str(value.get("status", "")))
            if status not in VALID_STATUS_EFFECTS:
                return None
            expires_turn = value.get("expires_turn", 1)
            if not isinstance(expires_turn, (int, float)):
                expires_turn = 1
            if status == "badly_poisoned":
                bad_poison_turn = value.get("bad_poison_turn", 1)
                if not isinstance(bad_poison_turn, (int, float)):
                    bad_poison_turn = 1
                return [status, int(expires_turn), int(bad_poison_turn)]
            return [status, int(expires_turn)]

        if isinstance(value, list) and len(value) >= 2:
            status_raw, expires_turn_raw = value[0], value[1]
            status = normalize_status_name(status_raw)
            if status not in VALID_STATUS_EFFECTS:
                return None
            if not isinstance(expires_turn_raw, (int, float)):
                return None
            if status == "badly_poisoned":
                bad_poison_turn_raw = value[2] if len(value) >= 3 else 1
                if not isinstance(bad_poison_turn_raw, (int, float)):
                    bad_poison_turn_raw = 1
                return [status, int(expires_turn_raw), int(bad_poison_turn_raw)]
            return [status, int(expires_turn_raw)]

        if isinstance(value, str):
            status = normalize_status_name(value)
            if status in VALID_STATUS_EFFECTS:
                return [status, 1]

        return None

    if raw is None:
        return []

    # Canonical: [status, turns]
    parsed = parse_single_status(raw)
    if parsed:
        return parsed

    # Backwards compatibility: nested arrays/lists with first valid entry
    if isinstance(raw, list):
        for entry in raw:
            parsed_entry = parse_single_status(entry)
            if parsed_entry:
                return parsed_entry

    return []


def normalize_states(raw: list | str | None) -> list:
    if raw is None:
        return []

    if isinstance(raw, str):
        state = raw.strip().lower()
        return [state, 1] if state else []

    if isinstance(raw, list) and len(raw) >= 2:
        state = str(raw[0]).strip().lower()
        turns_remaining = raw[1]
        if not state or not isinstance(turns_remaining, (int, float)):
            return []
        return [state, int(turns_remaining)]

    return []


def unit_has_active_named_state(unit: GameUnit, state_name: str) -> bool:
    state_name = str(state_name or "").strip().lower()
    current_state = normalize_states(unit.states)
    return bool(
        current_state
        and str(current_state[0]).lower() == state_name
        and int(current_state[1]) > 0
    )


def apply_state_effect(unit: GameUnit, state_name: str, db: Session) -> bool:
    state_name = str(state_name or "").strip().lower()
    if state_name not in VALID_STATE_EFFECTS:
        return False

    current_state = normalize_states(unit.states)
    has_active_state = len(current_state) == 2 and int(current_state[1]) > 0

    # Special-case Power Trick: if applying while already present, remove it (toggle)
    try:
        if state_name == "power_trick" and current_state and current_state[0] == "power_trick" and int(current_state[1]) > 0:
            unit.states = []
            db.add(unit)
            return True
    except Exception:
        pass

    # Do not refresh an identical active state on this unit.
    if unit_has_active_named_state(unit, state_name):
        return False

    if has_active_state:
        return False

    if state_name in SIDE_SCREEN_STATE_NAMES:
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "aqua_ring":
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "ingrain":
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "laser_focus":
        unit.states = [state_name, 1]
    elif state_name == "heal_block":
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "cursed":
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "nightmare":
        # Nightmare persists while the unit is asleep; use a long duration and remove when sleep ends
        unit.states = [state_name, 9999]
    elif state_name == "immobilized":
        # Prevents movement for 3 turns but does not prevent using moves
        unit.states = [state_name, 3]
    elif state_name == "salt_cure":
        # Salt Cure lasts SCREEN_EFFECT_DURATION turns
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "taunt":
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "torment":
        # Torment prevents the unit from using the same move twice in a row
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "telekinesis":
        # Telekinesis makes moves (except OHKO moves) always hit this unit
        # and prevents Ground-type moves from hitting it.
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "tar_shot":
        # Tar Shot increases damage taken from Fire-type moves
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "gastro_acid":
        # Gastro Acid suppresses the unit's ability
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "embargo":
        # Embargo prevents the unit from using its held item
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "drowsy":
        # Drowsy expires after two full rounds (two turns per player)
        duration = 2
        try:
            gs = db.query(GameState).filter(GameState.game_id == unit.game_id).first()
            if gs and isinstance(gs.players, list) and len(gs.players) > 0:
                duration = 2 * len(gs.players)
        except Exception:
            duration = 2
        unit.states = [state_name, duration]
    elif state_name == "torment":
        # Torment prevents the unit from using the same move twice in a row
        unit.states = [state_name, SCREEN_EFFECT_DURATION]
    elif state_name == "destiny_bond":
        # Destiny Bond lasts until the unit can move again (tracked as 1 turn)
        unit.states = [state_name, 1]
    elif state_name == "confusion":
        unit.states = [state_name, random.randint(2, 5)]
    elif state_name == "flinch":
        unit.states = [state_name, 1]
    elif state_name == "glaive_rush":
        unit.states = [state_name, 1]
    elif state_name == "substitute":
        unit.states = [state_name, 9999]
    db.add(unit)
    return True


def apply_confusion_self_damage(
    unit: GameUnit,
    db: Session,
    game: Game | None = None,
    game_state: GameState | None = None,
) -> int:
    current_stats = unit.current_stats if isinstance(unit.current_stats, dict) else {}
    max_hp = int(current_stats.get("hp", 0) or 0)
    if max_hp <= 0:
        return 0

    attack = int(current_stats.get("attack", 0) or 0)
    defense = int(current_stats.get("defense", 1) or 1)
    safe_defense = defense if defense > 0 else 1
    level = int(unit.level or 0)
    random_factor = random.randint(85, 100) / 100
    base_damage = (((2 * level) / 5 + 2) * 40 * (attack / safe_defense)) / 50 + 2
    damage = max(1, min(max_hp, int(base_damage * random_factor)))

    unit.current_hp = max(0, int(unit.current_hp or 0) - damage)
    db.add(unit)

    if game and game_state:
        publish_system_log_event(
            game.link,
            f"{get_unit_display_name(unit, db)} hits themselves in confusion for {damage} damage",
            game_state,
            db,
        )

    return damage


def get_status_duration(status: str) -> int:
    if status in SHORT_DURATION_STATUS_EFFECTS:
        return random.randint(2, 4)
    return random.randint(4, 7)


def get_unit_types(unit: GameUnit, db: Session) -> set[str]:
    if unit.unit and isinstance(unit.unit.types, list):
        return {str(unit_type).lower() for unit_type in unit.unit.types}

    if unit.unit_id:
        unit_info = db.query(Unit).filter_by(id=unit.unit_id).first()
        if unit_info and isinstance(unit_info.types, list):
            return {str(unit_type).lower() for unit_type in unit_info.types}

    return set()


def is_status_immune_by_type(unit: GameUnit, status: str, db: Session) -> bool:
    immune_types = STATUS_TYPE_IMMUNITIES.get(status)
    if not immune_types:
        return False
    unit_types = get_unit_types(unit, db)
    return any(unit_type in immune_types for unit_type in unit_types)


def get_unit_ability_names(unit: GameUnit, db: Session) -> set[str]:
    """Return a set containing the active ability name for the given unit (lowercased)."""
    ability_id = get_unit_ability_id(unit)
    if ability_id is None:
        return set()
    try:
        ability = db.query(Ability).filter(Ability.id == ability_id).first()
        if ability and getattr(ability, "name", None):
            return {str(ability.name).lower()}
    except Exception:
        pass
    return set()


def is_ability_suppressed(unit: GameUnit) -> bool:
    """Return True if the unit currently has Gastro Acid (ability suppressed)."""
    try:
        s = normalize_states(unit.states)
        return bool(s and s[0] == 'gastro_acid' and int(s[1]) > 0)
    except Exception:
        return False


def is_item_suppressed(unit: GameUnit) -> bool:
    """Return True if the unit currently has Embargo (item use suppressed)."""
    try:
        s = normalize_states(unit.states)
        return bool(s and s[0] == 'embargo' and int(s[1]) > 0)
    except Exception:
        return False


def apply_status_effect(unit: GameUnit, status: str, db: Session) -> bool:
    status = normalize_status_name(status)
    if status not in VALID_STATUS_EFFECTS:
        return False

    current_status_effects = normalize_status_effects(unit.status_effects)
    has_active_status = len(current_status_effects) == 2 and int(current_status_effects[1]) > 0
    if has_active_status:
        return False

    if is_status_immune_by_type(unit, status, db):
        return False

    duration = get_status_duration(status)
    if status == "badly_poisoned":
        unit.status_effects = [status, duration, 1]
    else:
        unit.status_effects = [status, duration]

    unit.current_stats = compute_effective_stats(unit, db)
    db.add(unit)
    return True


def cure_status_effect(unit: GameUnit, status_spec: str, db: Session) -> bool:
    """Cure a unit's current status when it matches status_spec."""
    current_status_effects = normalize_status_effects(unit.status_effects)
    if not current_status_effects:
        return False

    current_status_name = str(current_status_effects[0]).lower()
    normalized_spec = str(status_spec or "").strip().lower()

    should_cure = False
    if normalized_spec in {"all", "any"}:
        should_cure = True
    else:
        requested_statuses = {
            normalize_status_name(token)
            for token in normalized_spec.split(",")
            if token and token.strip()
        }
        should_cure = current_status_name in requested_statuses

    if not should_cure:
        return False

    unit.status_effects = []
    unit.current_stats = compute_effective_stats(unit, db)
    db.add(unit)
    return True


def matches_effect_condition(unit: GameUnit, condition: str, value: str, db: Session) -> bool:
    condition_name = str(condition or "").lower()
    condition_value = str(value or "").lower()
    if not condition_value:
        return False

    unit_types = get_unit_types(unit, db)
    if condition_name == "type":
        return condition_value in unit_types
    if condition_name == "not_type":
        return condition_value not in unit_types

    # Ability checks: support 'has_ability' and 'not_has_ability'
    if condition_name == "has_ability":
        # If Gastro Acid is active, abilities are suppressed
        if is_ability_suppressed(unit):
            return False
        requested = {token.strip().lower() for token in condition_value.split(",") if token.strip()}
        if not requested:
            return False
        unit_abilities = get_unit_ability_names(unit, db)
        return any(req in unit_abilities for req in requested)
    if condition_name == "not_has_ability":
        if is_ability_suppressed(unit):
            # If abilities suppressed, treat as not having the ability
            return True
        requested = {token.strip().lower() for token in condition_value.split(",") if token.strip()}
        if not requested:
            return False
        unit_abilities = get_unit_ability_names(unit, db)
        return all(req not in unit_abilities for req in requested)

    if condition_name == "stat_boosted":
        return unit_has_positive_stat_stage(unit)

    if condition_name == "stat_raised_since_turn":
        return unit_stats_raised_since_turn_start(unit)

    return False


def normalize_stat_boosts(raw: dict | None) -> dict:
    normalized = default_stat_boosts()
    if not isinstance(raw, dict):
        return normalized

    for raw_stat, value in raw.items():
        stat = normalize_stat_name(str(raw_stat))
        if stat not in normalized:
            continue

        if isinstance(value, list):
            clean_instances = []
            for instance in value:
                if not isinstance(instance, dict):
                    continue
                magnitude = instance.get("magnitude")
                if not isinstance(magnitude, (int, float)):
                    continue
                expires_turn = instance.get("expires_turn", 4)
                if not isinstance(expires_turn, (int, float)):
                    expires_turn = 4
                clean_instances.append({
                    "magnitude": int(magnitude),
                    "expires_turn": int(expires_turn),
                })
            normalized[stat] = clean_instances
        elif isinstance(value, (int, float)):
            # Backwards compatibility for old stage-based payloads (e.g. {"attack": 1})
            stage_value = int(value)
            if stage_value != 0:
                normalized[stat] = [{"magnitude": stage_value, "expires_turn": 4}]

    return normalized

def get_stat_multiplier(stat_boosts: dict, stat: str) -> float:
    """
    Calculate the multiplier for a stat based on its boost/debuff stages.
    Uses standard Pokémon stat stage formula:
    - For positive stages: (2 + stage) / 2
    - For negative stages: 2 / (2 - stage)
    - Stage is capped at ±6
    """
    stat = normalize_stat_name(stat)
    boosts = normalize_stat_boosts(stat_boosts)
    
    if stat not in boosts:
        return 1.0
    
    instances = boosts.get(stat, [])
    if not instances:
        return 1.0
    
    # Sum all magnitudes from active instances
    total_stage = sum(inst.get("magnitude", 0) for inst in instances)
    
    # Cap at ±6
    total_stage = max(-6, min(6, total_stage))
    
    # Calculate multiplier
    if total_stage == 0:
        return 1.0
    elif total_stage > 0:
        return (2 + total_stage) / 2
    else:  # total_stage < 0
        return 2 / (2 - total_stage)


def get_stat_stage(stat_boosts: dict, stat: str) -> int:
    """Return summed stat stage for the stat, clamped to +/- 6."""
    stat = normalize_stat_name(stat)
    boosts = normalize_stat_boosts(stat_boosts)
    if stat not in boosts:
        return 0

    instances = boosts.get(stat, [])
    if not isinstance(instances, list):
        return 0

    total_stage = 0
    for inst in instances:
        if isinstance(inst, dict):
            magnitude = inst.get("magnitude", 0)
            if isinstance(magnitude, (int, float)):
                total_stage += int(magnitude)

    return max(-6, min(6, total_stage))


def get_accuracy_stage_multiplier(attacker_accuracy_stage: int, target_evasion_stage: int) -> float:
    """
    Gen V+ style accuracy/evasion multiplier.
    Uses adjusted stage = attacker accuracy stage - target evasion stage (clamped to +/- 6).
    """
    adjusted_stage = max(-6, min(6, attacker_accuracy_stage - target_evasion_stage))
    if adjusted_stage >= 0:
        return (3 + adjusted_stage) / 3
    return 3 / (3 - adjusted_stage)


def get_modified_accuracy_threshold(
    move_accuracy: int | None,
    attacker: GameUnit,
    target: GameUnit,
    *,
    special_tiles: list | None = None,
    attacker_types: set[str] | None = None,
    target_types: set[str] | None = None,
    target_ability_names: set[str] | None = None,
) -> float | None:
    """
    Compute the hit threshold from move base accuracy and accuracy/evasion stages.
    Returns None for perfect-accuracy moves.
    """
    if move_accuracy is None:
        return None

    try:
        base_accuracy = float(move_accuracy)
    except (TypeError, ValueError):
        return None

    attacker_accuracy_stage = get_stat_stage(attacker.stat_boosts, "accuracy")
    target_evasion_stage = get_stat_stage(target.stat_boosts, "evasion")
    stage_multiplier = get_accuracy_stage_multiplier(attacker_accuracy_stage, target_evasion_stage)

    modifier = 1.0
    if special_tiles is not None and target_types is not None:
        modifier *= get_grass_incoming_accuracy_multiplier(
            special_tiles,
            int(target.current_x),
            int(target.current_y),
            target_types,
            target_ability_names,
        )
    return max(0.0, base_accuracy * modifier * stage_multiplier)


def move_lands_on_target(
    move: Move,
    attacker: GameUnit,
    target: GameUnit,
    *,
    special_tiles: list | None = None,
    weather_tiles: list | None = None,
    attacker_types: set[str] | None = None,
    target_types: set[str] | None = None,
    target_ability_names: set[str] | None = None,
) -> bool:
    """
    True if move lands on target based on modified accuracy threshold.
    If move has no accuracy (null), it is treated as perfect accuracy.
    """
    if unit_has_glaive_rush(target):
        return True

    threshold = get_modified_accuracy_threshold(
        resolve_move_accuracy(move, target, weather_tiles),
        attacker,
        target,
        special_tiles=special_tiles,
        attacker_types=attacker_types,
        target_types=target_types,
        target_ability_names=target_ability_names,
    )
    if threshold is None:
        return True
    if threshold <= 0:
        return False
    if threshold >= 100:
        return True

    roll = random.uniform(0, 100)
    return roll <= threshold

def get_critical_hit_chance(crit_stage: int) -> float:
    """
    Get the critical hit chance based on crit stage.
    Uses Pokémon Gen III-V critical hit rates.
    Stages are clamped to -6 to +4 range.
    
    Stage thresholds:
    - Stage 0: 1/16 (6.25%)
    - Stage 1: 1/8 (12.5%)
    - Stage 2: 1/4 (25%)
    - Stage 3: 1/3 (~33.3%)
    - Stage 4+: 1/2 (50%)
    - Negative stages: 0% (impossible to crit)
    """
    # Clamp stage to reasonable range
    stage = max(-6, min(4, crit_stage))
    
    if stage < 0:
        return 0.0
    elif stage == 0:
        return 1 / 16  # 6.25%
    elif stage == 1:
        return 1 / 8   # 12.5%
    elif stage == 2:
        return 1 / 4   # 25%
    elif stage == 3:
        return 1 / 3   # ~33.3%
    else:  # stage >= 4
        return 1 / 2   # 50%

def move_has_high_crit_ratio(move: Move) -> bool:
    """Return True when a move includes a high_crit_ratio effect token."""
    if not move or not isinstance(move.effects, list):
        return False

    for effect in move.effects:
        token = str(effect or "").strip().lower()
        if token == "high_crit_ratio":
            return True
        if token.endswith(":high_crit_ratio"):
            return True
    return False


def move_is_instant_ko(move: Move) -> bool:
    """Return True if the move has an instant KO effect (e.g., Sheer Cold, Fissure)."""
    if not move or not isinstance(move.effects, list):
        return False

    for effect in move.effects:
        token = str(effect or "").strip().lower()
        if token == "target:instant_ko" or token.endswith(":instant_ko") or ":instant_ko" in token:
            return True
    return False


def move_has_target_fixed_damage_effect(move: Move) -> bool:
    """Return True when a move has a target fixed-damage effect token."""
    if not move or not isinstance(move.effects, list):
        return False

    for effect in move.effects:
        token = str(effect or "").strip().lower()
        if token.startswith("target:fixed_damage:"):
            return True
    return False


def compute_fixed_damage_effect(effect_str: str, attacker: GameUnit, target: GameUnit) -> int:
    """Resolve fixed-damage amount from an effect string for a specific attacker/target pair."""
    parts = str(effect_str or "").split(":")
    if len(parts) < 3:
        return 0

    effect_mode = str(parts[2] or "").strip().lower()
    attacker_hp = max(0, int(attacker.current_hp or 0))
    target_hp = max(0, int(target.current_hp or 0))

    raw_damage = 0
    if effect_mode == "level":
        raw_damage = max(0, int(attacker.level or 0))
    elif effect_mode == "equal_to_user_hp":
        raw_damage = attacker_hp
    elif effect_mode == "reduce_to_user_hp":
        raw_damage = max(0, target_hp - attacker_hp)
    elif effect_mode == "current_hp":
        if len(parts) < 4:
            return 0
        try:
            denominator = int(parts[3])
            if denominator <= 0:
                return 0
        except ValueError:
            return 0
        raw_damage = target_hp // denominator
        if target_hp > 0:
            raw_damage = max(1, raw_damage)
    elif effect_mode == "last_damage_received":
        if len(parts) < 4:
            return 0
        try:
            multiplier = float(parts[3])
        except ValueError:
            return 0
        flags = get_unit_flags(attacker)
        try:
            last_damage = int(flags.get("last_damage_amount", 0) or 0)
        except (TypeError, ValueError):
            last_damage = 0
        if last_damage <= 0:
            return 0
        raw_damage = max(1, int(last_damage * multiplier))
    else:
        try:
            raw_damage = max(0, int(effect_mode))
        except ValueError:
            return 0

    return min(target_hp, raw_damage)


def apply_fixed_damage_move_effects(
    move: Move,
    attacker: GameUnit,
    targets: List[GameUnit],
    db: Session,
    hit_count: int = 1,
) -> List[dict]:
    """Apply fixed-damage move effects to targets and return damage payload rows."""
    if not move or not isinstance(move.effects, list) or not targets:
        return []

    fixed_damage_effects = []
    for effect in move.effects:
        token = str(effect or "").strip().lower()
        if token.startswith("target:fixed_damage:"):
            fixed_damage_effects.append(effect)

    if not fixed_damage_effects:
        return []

    damage_results: List[dict] = []
    for target in targets:
        if (target.current_hp or 0) <= 0:
            continue

        total_damage = 0
        hits_to_apply = max(1, int(hit_count or 1))
        for _ in range(hits_to_apply):
            if (target.current_hp or 0) <= 0:
                break

            damage = 0
            for effect_str in fixed_damage_effects:
                damage = compute_fixed_damage_effect(effect_str, attacker, target)
                break

            if damage <= 0:
                continue

            target.current_hp = max(0, int(target.current_hp or 0) - damage)
            total_damage += damage
            record_last_damage_received(target, attacker, damage, db)

        db.add(target)
        damage_results.append({"id": target.id, "damage": total_damage, "current_hp": target.current_hp})

    return damage_results


def attempt_critical_hit(attacker: GameUnit, additional_stage: int = 0) -> bool:
    """
    Determine if an attack is a critical hit based on attacker's crit stage.
    Returns True if the attack should be a critical hit, False otherwise.
    """
    crit_stage = get_stat_stage(attacker.stat_boosts, "crit") + int(additional_stage or 0)
    crit_chance = get_critical_hit_chance(crit_stage)
    
    if crit_chance <= 0:
        return False
    if crit_chance >= 1.0:
        return True
    
    roll = random.random()
    return roll < crit_chance

def compute_effective_stats(unit: GameUnit, db: Session) -> dict:
    """
    Compute the effective stats for a unit, applying stat boost multipliers.
    Returns a dict with all stats including HP, attack, defense, etc.
    """
    # Get base stats from the unit definition
    unit_info = db.query(Unit).filter_by(id=unit.unit_id).first()
    if not unit_info or not isinstance(unit_info.base_stats, dict):
        return unit.current_stats or {}
    
    level = unit.level or 50
    effective_stats = {}
    
    for stat_name, base_value in unit_info.base_stats.items():
        # Calculate base stat value (without boosts)
        if stat_name.lower() == "hp":
            # HP formula: floor((2 × Base × Level) / 100) + Level + 10
            base_stat = int((2 * base_value * level) / 100) + level + 10
            # HP is not affected by stat boosts in battle
            effective_stats[stat_name] = base_stat
        elif stat_name.lower() == "range":
            # Range is derived from speed after all modifiers - will be calculated below
            continue
        else:
            # Other stats formula: floor((2 × Base × Level) / 100 + 5)
            base_stat = int((2 * base_value * level) / 100 + 5)
            
            # Apply stat boost multiplier
            multiplier = get_stat_multiplier(unit.stat_boosts, stat_name)
            effective_stats[stat_name] = int(base_stat * multiplier)

    # Apply status modifiers after boost/debuff calculations.
    # Check for Tailwind on the unit's side and apply speed doubling before status modifiers
    try:
        side_units = (
            db.query(GameUnit)
            .filter(GameUnit.game_id == unit.game_id, GameUnit.user_id == unit.user_id)
            .all()
        )
    except Exception:
        side_units = []

    has_tailwind = False
    for su in side_units:
        s = normalize_states(su.states)
        if s and s[0] == "tailwind" and int(s[1]) > 0:
            has_tailwind = True
            break

    if has_tailwind and "speed" in effective_stats:
        effective_stats["speed"] = int(effective_stats["speed"] * 2)

    status_effect = normalize_status_effects(unit.status_effects)
    if status_effect:
        status_name = status_effect[0]
        if status_name == "burn" and "attack" in effective_stats:
            effective_stats["attack"] = int(effective_stats["attack"] // 2)
        elif status_name == "paralysis" and "speed" in effective_stats:
            effective_stats["speed"] = int(effective_stats["speed"] // 2)

    # Movement range scales with current speed (after boosts/debuffs/status).
    speed_value = effective_stats.get("speed")
    if isinstance(speed_value, (int, float)) and speed_value > 0:
        effective_stats["range"] = max(0, int(2 + (speed_value / 50)))
    else:
        effective_stats["range"] = 0
    
    # Ensure no stat keys are missing by comparing against base_stats
    for stat_name in unit_info.base_stats.keys():
        if stat_name not in effective_stats:
            # Fallback: if a stat key is missing, recalculate it
            base_value = unit_info.base_stats[stat_name]
            if stat_name.lower() == "hp":
                effective_stats[stat_name] = int((2 * base_value * level) / 100) + level + 10
            elif stat_name.lower() == "range":
                # range already calculated above
                if "range" not in effective_stats:
                    effective_stats["range"] = 0
            else:
                base_stat = int((2 * base_value * level) / 100 + 5)
                multiplier = get_stat_multiplier(unit.stat_boosts, stat_name)
                effective_stats[stat_name] = int(base_stat * multiplier)
    
    return effective_stats

def apply_stat_change(unit: GameUnit, stat: str, magnitude: int, current_turn: int, db: Session):
    """
    Apply or cancel a stat change to a unit.
    - magnitude: positive for boost, negative for debuff
    - Implements cancellation: opposite effects cancel, prioritizing soonest-expiring
    - Handles partial cancellation when magnitudes differ
    - Each instance expires after 4 turns (including application turn)
    """
    stat = normalize_stat_name(stat)
    
    # Ensure stat_boosts is always in canonical list-of-instances shape
    unit.stat_boosts = normalize_stat_boosts(unit.stat_boosts)
    if stat not in unit.stat_boosts:
        unit.stat_boosts[stat] = []
    
    instances = unit.stat_boosts[stat]
    remaining_magnitude = magnitude
    
    # Process cancellation with opposite-sign effects (already in expiry order)
    i = 0
    while i < len(instances) and remaining_magnitude != 0:
        instance_mag = instances[i].get("magnitude", 0)
        
        # Check if signs are opposite (cancellation applies)
        if (remaining_magnitude > 0 and instance_mag < 0) or (remaining_magnitude < 0 and instance_mag > 0):
            # Calculate how much can be cancelled
            abs_incoming = abs(remaining_magnitude)
            abs_existing = abs(instance_mag)
            
            if abs_incoming < abs_existing:
                # Incoming is smaller: reduce existing magnitude
                if instance_mag < 0:
                    instances[i]["magnitude"] = instance_mag + abs_incoming  # e.g., -3 + 2 = -1
                else:
                    instances[i]["magnitude"] = instance_mag - abs_incoming  # e.g., +3 - 2 = +1
                remaining_magnitude = 0  # Fully consumed
                i += 1
            elif abs_incoming > abs_existing:
                # Incoming is larger: remove existing, continue with remainder
                if remaining_magnitude > 0:
                    remaining_magnitude -= abs_existing  # e.g., +5 - 3 = +2
                else:
                    remaining_magnitude += abs_existing  # e.g., -5 + 3 = -2
                instances.pop(i)
                # Don't increment i, check next instance at same position
            else:
                # Equal: both cancel out completely
                instances.pop(i)
                remaining_magnitude = 0
        else:
            # Same sign, no cancellation
            i += 1
    
    # If there's remaining magnitude, add it as a new instance
    if remaining_magnitude != 0:
        # Set to 4 turns (will be decremented at start of each player turn)
        instances.append({
            "magnitude": remaining_magnitude,
            "expires_turn": 4
        })
    
    # Mark as modified for SQLAlchemy
    unit.stat_boosts = dict(unit.stat_boosts)
    
    # Recalculate current_stats to reflect the new stat boosts
    unit.current_stats = compute_effective_stats(unit, db)
    
    db.add(unit)

def process_move_effects(
    move: Move,
    attacker: GameUnit,
    targets: List[GameUnit],
    current_turn: int,
    db: Session,
    weather_tiles: list | None = None,
    terrain_tiles: list | None = None,
    field_effect_tiles: list | None = None,
    affected_tiles_override: list[tuple[int, int]] | None = None,
    game: "Game | None" = None,
    game_state: "GameState | None" = None,
):
    """
    Process all effects from a move (stat changes, status conditions, etc.)
    Format: recipient:effect_type:param1:param2[:accuracy]
    For stat changes: recipient:raise_stat/lower_stat:stat_name:magnitude[:accuracy]
    For conditional effects: recipient:effect_type:condition:condition_type:condition_value:...:value
    """
    if not move.effects:
        return

    weather_raise_stat_applied: set[tuple[str, str]] = set()
    terrain_raise_stat_applied: set[tuple[str, str]] = set()
    
    for effect_str in move.effects:
        raw_token = str(effect_str or "").strip()
        token_lower = raw_token.lower()

        # Special-case single-token effects
        if token_lower == "break_screens":
            # Remove reflect/light_screen/aurora_veil from each target's side
            for target in targets:
                try:
                    side_units = (
                        db.query(GameUnit)
                        .filter(GameUnit.game_id == target.game_id, GameUnit.user_id == target.user_id)
                        .all()
                    )
                except Exception:
                    side_units = []

                for u in side_units:
                    s = normalize_states(u.states)
                    if s and s[0] in {"reflect", "light_screen", "aurora_veil"}:
                        removed_state = s[0]
                        u.states = []
                        db.add(u)
                        if game and game_state:
                            publish_system_log_event(
                                game.link,
                                f"{get_unit_display_name(u, db)} lost {removed_state.replace('_', ' ')}",
                                game_state,
                                db,
                            )
            continue

        parts = raw_token.split(":")
        if len(parts) < 2:
            continue  # Invalid format

            # If this effect depends on a held item and the recipient's item is suppressed by Embargo,
            # skip applying the effect and publish a system log.
            try:
                if parts[0] in {"self", "target"} and any("held_item" == p or p == "held_item" for p in parts):
                    if parts[0] == "self":
                        if is_item_suppressed(attacker):
                            if game and game_state:
                                publish_system_log_event(game.link, f"{get_unit_display_name(attacker, db)}'s held item is suppressed by Embargo", game_state, db)
                            continue
                    elif parts[0] == "target":
                        # If any target is embargoed, skip applying this token for targets
                        embargoed = False
                        for t in targets:
                            if is_item_suppressed(t):
                                embargoed = True
                                if game and game_state:
                                    publish_system_log_event(game.link, f"{get_unit_display_name(t, db)}'s held item is suppressed by Embargo", game_state, db)
                        if embargoed:
                            continue
            except Exception:
                pass

        # Field weather effect format: weather:sun|rain|sandstorm|hail
        if parts[0] == "weather":
            weather_name = parts[1].lower()
            weather_id = WEATHER_TO_ID.get(weather_name)
            if weather_id is None:
                continue

            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_state = (
                db.query(GameMapState)
                .options(joinedload(GameMapState.map))
                .filter(GameMapState.game_id == game.id)
                .first()
            )
            if map_state is None:
                map_obj = db.query(Map).filter_by(id=game.map_id).first()
                if not map_obj:
                    continue
                map_state = _create_default_game_map_state(game, map_obj)
                db.add(map_state)
            else:
                map_obj = map_state.map if map_state.map else db.query(Map).filter_by(id=game.map_id).first()
            if not map_obj:
                continue

            height = int(getattr(map_obj, "height", 0) or 0)
            width = int(getattr(map_obj, "width", 0) or 0)
            if height <= 0 or width <= 0:
                continue

            if not isinstance(map_state.weather_tiles, list) or len(map_state.weather_tiles) != height:
                map_state.weather_tiles = _build_2d_matrix(height, width, 0)
            else:
                normalized_rows = []
                for row in map_state.weather_tiles:
                    if not isinstance(row, list):
                        normalized_rows.append([0 for _ in range(width)])
                    elif len(row) != width:
                        fixed = [0 for _ in range(width)]
                        for i in range(min(width, len(row))):
                            fixed[i] = int(row[i] or 0)
                        normalized_rows.append(fixed)
                    else:
                        normalized_rows.append([int(cell or 0) for cell in row])
                map_state.weather_tiles = normalized_rows

            if affected_tiles_override:
                seen_tiles: set[tuple[int, int]] = set()
                affected_tiles = []
                for tx, ty in affected_tiles_override:
                    if not (0 <= tx < width and 0 <= ty < height):
                        continue
                    tile = (int(tx), int(ty))
                    if tile in seen_tiles:
                        continue
                    seen_tiles.add(tile)
                    affected_tiles.append(tile)
            else:
                affected_tiles = get_move_affected_tiles(move, attacker, width, height)
            for tx, ty in affected_tiles:
                map_state.weather_tiles[ty][tx] = weather_id
            db.add(map_state)
            continue

        # Field terrain effect format: terrain:electric|psychic|grassy|misty
        if parts[0] == "terrain":
            terrain_name = parts[1].lower()
            terrain_id = TERRAIN_TO_ID.get(terrain_name)
            if terrain_id is None:
                continue

            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_state = (
                db.query(GameMapState)
                .options(joinedload(GameMapState.map))
                .filter(GameMapState.game_id == game.id)
                .first()
            )
            if map_state is None:
                map_obj = db.query(Map).filter_by(id=game.map_id).first()
                if not map_obj:
                    continue
                map_state = _create_default_game_map_state(game, map_obj)
                db.add(map_state)
            else:
                map_obj = map_state.map if map_state.map else db.query(Map).filter_by(id=game.map_id).first()
            if not map_obj:
                continue

            height = int(getattr(map_obj, "height", 0) or 0)
            width = int(getattr(map_obj, "width", 0) or 0)
            if height <= 0 or width <= 0:
                continue

            if not isinstance(map_state.terrain_effect_tiles, list) or len(map_state.terrain_effect_tiles) != height:
                map_state.terrain_effect_tiles = _build_2d_matrix(height, width, [0, 0])
            else:
                normalized_rows = []
                for row in map_state.terrain_effect_tiles:
                    if not isinstance(row, list):
                        normalized_rows.append([[0, 0] for _ in range(width)])
                    elif len(row) != width:
                        fixed = [[0, 0] for _ in range(width)]
                        for i in range(min(width, len(row))):
                            fixed[i] = normalize_timed_tile_cell(row[i])
                        normalized_rows.append(fixed)
                    else:
                        normalized_rows.append([normalize_timed_tile_cell(cell) for cell in row])
                map_state.terrain_effect_tiles = normalized_rows

            if affected_tiles_override:
                seen_tiles: set[tuple[int, int]] = set()
                affected_tiles = []
                for tx, ty in affected_tiles_override:
                    if not (0 <= tx < width and 0 <= ty < height):
                        continue
                    tile = (int(tx), int(ty))
                    if tile in seen_tiles:
                        continue
                    seen_tiles.add(tile)
                    affected_tiles.append(tile)
            else:
                affected_tiles = get_move_affected_tiles(move, attacker, width, height)
            for tx, ty in affected_tiles:
                map_state.terrain_effect_tiles[ty][tx] = [terrain_id, TERRAIN_DEFAULT_DURATION]
            db.add(map_state)
            continue

        # Field hazard effect format: field_hazard:spikes|toxic_spikes|stealth_rock|sticky_web
        if parts[0] == "field_hazard":
            hazard_name = parts[1].lower()
            hazard_id = FIELD_HAZARD_TO_ID.get(hazard_name)
            if hazard_id is None:
                continue

            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_state = (
                db.query(GameMapState)
                .options(joinedload(GameMapState.map))
                .filter(GameMapState.game_id == game.id)
                .first()
            )
            if map_state is None:
                map_obj = db.query(Map).filter_by(id=game.map_id).first()
                if not map_obj:
                    continue
                map_state = _create_default_game_map_state(game, map_obj)
                db.add(map_state)
            else:
                map_obj = map_state.map if map_state.map else db.query(Map).filter_by(id=game.map_id).first()
            if not map_obj:
                continue

            height = int(getattr(map_obj, "height", 0) or 0)
            width = int(getattr(map_obj, "width", 0) or 0)
            if height <= 0 or width <= 0:
                continue

            normalized_hazards: list[list[list[list[int]]]] = []
            for y in range(height):
                row = map_state.hazard_tiles[y] if isinstance(map_state.hazard_tiles, list) and y < len(map_state.hazard_tiles) else []
                normalized_row: list[list[list[int]]] = []
                for x in range(width):
                    cell = row[x] if isinstance(row, list) and x < len(row) else []
                    normalized_row.append(normalize_hazard_cell(cell))
                normalized_hazards.append(normalized_row)
            map_state.hazard_tiles = normalized_hazards

            if affected_tiles_override:
                seen_tiles: set[tuple[int, int]] = set()
                affected_tiles = []
                for tx, ty in affected_tiles_override:
                    if not (0 <= tx < width and 0 <= ty < height):
                        continue
                    tile = (int(tx), int(ty))
                    if tile in seen_tiles:
                        continue
                    seen_tiles.add(tile)
                    affected_tiles.append(tile)
            else:
                affected_tiles = get_move_affected_tiles(move, attacker, width, height)
            for tx, ty in affected_tiles:
                try_add_hazard_stack(
                    map_state.hazard_tiles[ty][tx],
                    hazard_id,
                    FIELD_HAZARD_DEFAULT_DURATION,
                )

            db.add(map_state)
            continue

        if parts[0] == "field" and parts[1].lower() == "clear_hazards":
            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_state = (
                db.query(GameMapState)
                .options(joinedload(GameMapState.map))
                .filter(GameMapState.game_id == game.id)
                .first()
            )
            if map_state is None:
                continue

            map_obj = map_state.map if map_state.map else db.query(Map).filter_by(id=game.map_id).first()
            if not map_obj:
                continue

            height = int(getattr(map_obj, "height", 0) or 0)
            width = int(getattr(map_obj, "width", 0) or 0)
            if height <= 0 or width <= 0:
                continue

            if affected_tiles_override:
                affected_tiles = list(affected_tiles_override)
            else:
                affected_tiles = get_move_affected_tiles(move, attacker, width, height)

            if clear_hazards_on_tiles(map_state, affected_tiles, db) and game and game_state:
                publish_system_log_event(game.link, "Hazards were cleared from the area", game_state, db)
            continue

        if parts[0] == "field" and parts[1].lower() == "clear_substitutes":
            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_obj = db.query(Map).filter_by(id=game.map_id).first()
            if not map_obj:
                continue

            width = int(getattr(map_obj, "width", 0) or 0)
            height = int(getattr(map_obj, "height", 0) or 0)
            if width <= 0 or height <= 0:
                continue

            if affected_tiles_override:
                affected_tiles = list(affected_tiles_override)
            else:
                affected_tiles = get_move_affected_tiles(move, attacker, width, height)

            clear_substitutes_on_tiles(game_id, affected_tiles, db, game=game, game_state=game_state)
            continue

        if parts[0] == "self" and parts[1].lower() == "clear_hazards":
            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_state = db.query(GameMapState).filter(GameMapState.game_id == game.id).first()
            if map_state is None:
                continue

            tx = int(attacker.current_x)
            ty = int(attacker.current_y)
            clear_hazards_on_tiles(map_state, [(tx, ty)], db)
            continue

        # Field tailwind: apply tailwind to the attacker's side
        if parts[0] == "field" and parts[1].lower() == "tailwind":
            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            # Apply tailwind to the attacker (represents side-wide effect)
            applied = apply_state_effect(attacker, "tailwind", db)
            if applied and game and game_state:
                publish_system_log_event(
                    game.link,
                    format_state_log_message(attacker, "tailwind", db),
                    game_state,
                    db,
                )
            continue

        if parts[0] == "field" and parts[1].lower() == "gravity":
            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_state = (
                db.query(GameMapState)
                .options(joinedload(GameMapState.map))
                .filter(GameMapState.game_id == game.id)
                .first()
            )
            if map_state is None:
                map_obj = db.query(Map).filter_by(id=game.map_id).first()
                if not map_obj:
                    continue
                map_state = _create_default_game_map_state(game, map_obj)
                db.add(map_state)
            else:
                map_obj = map_state.map if map_state.map else db.query(Map).filter_by(id=game.map_id).first()
            if not map_obj:
                continue

            height = int(getattr(map_obj, "height", 0) or 0)
            width = int(getattr(map_obj, "width", 0) or 0)
            if height <= 0 or width <= 0:
                continue

            if not isinstance(map_state.field_effect_tiles, list) or len(map_state.field_effect_tiles) != height:
                map_state.field_effect_tiles = _build_2d_matrix(height, width, 0)

            gravity_id = FIELD_EFFECT_TO_ID.get("gravity", 0)
            if affected_tiles_override:
                affected_tiles = affected_tiles_override
            else:
                affected_tiles = get_move_affected_tiles(move, attacker, width, height)
            for tx, ty in affected_tiles:
                if 0 <= tx < width and 0 <= ty < height:
                    map_state.field_effect_tiles[ty][tx] = gravity_id
            db.add(map_state)
            continue

        if parts[0] in {"self", "target"} and parts[1] == "consume_berry":
            recipients = [attacker] if parts[0] == "self" else targets
            for unit in recipients:
                if consume_unit_held_item(unit, db, item_type="berry") and game and game_state:
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(unit, db)} ate its Berry",
                        game_state,
                        db,
                    )
            continue

        if parts[0] == "target" and parts[1] == "remove_held_item":
            for target in targets:
                if remove_unit_held_item(target, db) and game and game_state:
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(target, db)} lost its held item",
                        game_state,
                        db,
                    )
            continue

        if parts[0] == "target" and parts[1] == "field_hazard" and len(parts) >= 3:
            hazard_name = parts[2].lower()
            hazard_id = FIELD_HAZARD_TO_ID.get(hazard_name)
            if hazard_id is None:
                continue

            game_id = getattr(attacker, "game_id", None)
            if not isinstance(game_id, int):
                continue

            game = db.query(Game).filter(Game.id == game_id).first()
            if not game:
                continue

            map_state = (
                db.query(GameMapState)
                .options(joinedload(GameMapState.map))
                .filter(GameMapState.game_id == game.id)
                .first()
            )
            if map_state is None:
                continue

            map_obj = map_state.map if map_state.map else db.query(Map).filter_by(id=game.map_id).first()
            if not map_obj:
                continue

            height = int(getattr(map_obj, "height", 0) or 0)
            width = int(getattr(map_obj, "width", 0) or 0)
            if height <= 0 or width <= 0:
                continue

            normalized_hazards: list[list[list[list[int]]]] = []
            for y in range(height):
                row = map_state.hazard_tiles[y] if isinstance(map_state.hazard_tiles, list) and y < len(map_state.hazard_tiles) else []
                normalized_row: list[list[list[int]]] = []
                for x in range(width):
                    cell = row[x] if isinstance(row, list) and x < len(row) else []
                    normalized_row.append(normalize_hazard_cell(cell))
                normalized_hazards.append(normalized_row)
            map_state.hazard_tiles = normalized_hazards

            for target in targets:
                tx = int(target.current_x)
                ty = int(target.current_y)
                if 0 <= tx < width and 0 <= ty < height:
                    try_add_hazard_stack(
                        map_state.hazard_tiles[ty][tx],
                        hazard_id,
                        FIELD_HAZARD_DEFAULT_DURATION,
                    )
            db.add(map_state)
            continue
        
        recipient = parts[0]  # "self" or "target"
        effect_type = parts[1]  # "raise_stat", "lower_stat", etc.

        if effect_type in ["raise_stat", "lower_stat"]:
            stat_name = None
            magnitude_val = None
            accuracy = 100

            # Format: recipient:raise_stat:condition:weather:condition_value:stat_name:magnitude[:accuracy]
            if len(parts) >= 7 and parts[2] == "condition" and parts[3].lower() == "weather":
                condition_value = parts[4]
                stat_name = normalize_stat_name(parts[5])
                try:
                    magnitude_val = int(parts[6])
                except ValueError:
                    continue

                weather_key = (recipient, stat_name)
                if weather_key in weather_raise_stat_applied:
                    continue

                if recipient == "self":
                    weather_id = get_unit_weather_id(attacker, weather_tiles)
                elif recipient == "target":
                    if not targets:
                        continue
                    weather_id = get_unit_weather_id(targets[0], weather_tiles)
                else:
                    continue

                if not weather_condition_matches(weather_id, condition_value):
                    continue

                weather_raise_stat_applied.add(weather_key)

                if len(parts) >= 8:
                    try:
                        accuracy = int(parts[7])
                    except ValueError:
                        pass
            elif len(parts) >= 7 and parts[2] == "condition" and parts[3].lower() == "terrain":
                condition_value = parts[4]
                stat_name = normalize_stat_name(parts[5])
                try:
                    magnitude_val = int(parts[6])
                except ValueError:
                    continue

                terrain_key = (recipient, stat_name)
                if terrain_key in terrain_raise_stat_applied:
                    continue

                if recipient == "self":
                    terrain_id = get_unit_terrain_id(attacker, terrain_tiles)
                elif recipient == "target":
                    if not targets:
                        continue
                    terrain_id = get_unit_terrain_id(targets[0], terrain_tiles)
                else:
                    continue

                if not terrain_condition_matches(terrain_id, condition_value):
                    continue

                terrain_raise_stat_applied.add(terrain_key)

                if len(parts) >= 8:
                    try:
                        accuracy = int(parts[7])
                    except ValueError:
                        pass
            elif len(parts) >= 7 and parts[2] == "condition" and parts[3].lower() == "is_type":
                condition_value = parts[4]
                stat_name = normalize_stat_name(parts[5])
                try:
                    magnitude_val = int(parts[6])
                except ValueError:
                    continue

                if len(parts) >= 8:
                    try:
                        accuracy = int(parts[7])
                    except ValueError:
                        pass

                if recipient == "self":
                    if not matches_effect_condition(attacker, "type", condition_value, db):
                        continue
                elif recipient == "target":
                    if not targets:
                        continue
                    filtered_targets = [
                        target for target in targets
                        if matches_effect_condition(target, "type", condition_value, db)
                    ]
                    if not filtered_targets:
                        continue
                    targets_for_effect = filtered_targets
                else:
                    continue

                if random.randint(1, 100) > accuracy:
                    continue

                magnitude = magnitude_val if effect_type == "raise_stat" else -magnitude_val
                target_stats = ALL_STAT_EFFECT_KEYS if stat_name == "all" else [stat_name]

                if recipient == "self":
                    for target_stat in target_stats:
                        before_stage = get_stat_stage(attacker.stat_boosts, target_stat)
                        apply_stat_change(attacker, target_stat, magnitude, current_turn, db)
                        after_stage = get_stat_stage(attacker.stat_boosts, target_stat)
                        if game and game_state:
                            outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1 if magnitude > 0 else -1)
                            publish_system_log_event(
                                game.link,
                                f"{get_unit_display_name(attacker, db)}'s {format_stat_log_label(target_stat)} {outcome_phrase}",
                                game_state,
                                db,
                            )
                elif recipient == "target":
                    for target in targets_for_effect:
                        for target_stat in target_stats:
                            before_stage = get_stat_stage(target.stat_boosts, target_stat)
                            apply_stat_change(target, target_stat, magnitude, current_turn, db)
                            after_stage = get_stat_stage(target.stat_boosts, target_stat)
                            if game and game_state:
                                outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1 if magnitude > 0 else -1)
                                publish_system_log_event(
                                    game.link,
                                    f"{get_unit_display_name(target, db)}'s {format_stat_log_label(target_stat)} {outcome_phrase}",
                                    game_state,
                                    db,
                                )
                continue
            elif len(parts) >= 7 and parts[2] == "condition" and parts[3].lower() == "not_type":
                condition_value = parts[4]
                stat_name = normalize_stat_name(parts[5])
                try:
                    magnitude_val = int(parts[6])
                except ValueError:
                    continue

                if len(parts) >= 8:
                    try:
                        accuracy = int(parts[7])
                    except ValueError:
                        pass

                if recipient == "self":
                    if not matches_effect_condition(attacker, "not_type", condition_value, db):
                        continue
                elif recipient == "target":
                    if not targets:
                        continue
                    filtered_targets = [
                        target for target in targets
                        if matches_effect_condition(target, "not_type", condition_value, db)
                    ]
                    if not filtered_targets:
                        continue
                    targets_for_effect = filtered_targets
                else:
                    continue

                if random.randint(1, 100) > accuracy:
                    continue

                magnitude = magnitude_val if effect_type == "raise_stat" else -magnitude_val
                target_stats = ALL_STAT_EFFECT_KEYS if stat_name == "all" else [stat_name]

                if recipient == "self":
                    for target_stat in target_stats:
                        before_stage = get_stat_stage(attacker.stat_boosts, target_stat)
                        apply_stat_change(attacker, target_stat, magnitude, current_turn, db)
                        after_stage = get_stat_stage(attacker.stat_boosts, target_stat)
                        if game and game_state:
                            outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1 if magnitude > 0 else -1)
                            publish_system_log_event(
                                game.link,
                                f"{get_unit_display_name(attacker, db)}'s {format_stat_log_label(target_stat)} {outcome_phrase}",
                                game_state,
                                db,
                            )
                elif recipient == "target":
                    for target in targets_for_effect:
                        for target_stat in target_stats:
                            before_stage = get_stat_stage(target.stat_boosts, target_stat)
                            apply_stat_change(target, target_stat, magnitude, current_turn, db)
                            after_stage = get_stat_stage(target.stat_boosts, target_stat)
                            if game and game_state:
                                outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1 if magnitude > 0 else -1)
                                publish_system_log_event(
                                    game.link,
                                    f"{get_unit_display_name(target, db)}'s {format_stat_log_label(target_stat)} {outcome_phrase}",
                                    game_state,
                                    db,
                                )
                continue
            else:
                if len(parts) < 4:
                    continue

                stat_name = normalize_stat_name(parts[2])
                try:
                    magnitude_val = int(parts[3])
                except ValueError:
                    continue

                if len(parts) >= 5:
                    try:
                        accuracy = int(parts[4])
                    except ValueError:
                        pass

            if stat_name is None or magnitude_val is None:
                continue

            if random.randint(1, 100) > accuracy:
                continue

            magnitude = magnitude_val if effect_type == "raise_stat" else -magnitude_val
            target_stats = ALL_STAT_EFFECT_KEYS if stat_name == "all" else [stat_name]

            if recipient == "self":
                for target_stat in target_stats:
                    before_stage = get_stat_stage(attacker.stat_boosts, target_stat)
                    apply_stat_change(attacker, target_stat, magnitude, current_turn, db)
                    after_stage = get_stat_stage(attacker.stat_boosts, target_stat)
                    if game and game_state:
                        outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1 if magnitude > 0 else -1)
                        publish_system_log_event(
                            game.link,
                            f"{get_unit_display_name(attacker, db)}'s {format_stat_log_label(target_stat)} {outcome_phrase}",
                            game_state,
                            db,
                        )
            elif recipient == "target":
                for target in targets:
                    for target_stat in target_stats:
                        before_stage = get_stat_stage(target.stat_boosts, target_stat)
                        apply_stat_change(target, target_stat, magnitude, current_turn, db)
                        after_stage = get_stat_stage(target.stat_boosts, target_stat)
                        if game and game_state:
                            outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1 if magnitude > 0 else -1)
                            publish_system_log_event(
                                game.link,
                                f"{get_unit_display_name(target, db)}'s {format_stat_log_label(target_stat)} {outcome_phrase}",
                                game_state,
                                db,
                            )

        elif effect_type == "high_crit_ratio":
            # Format: recipient:high_crit_ratio[:accuracy]
            # Applies a +1 boost to the target's crit rate
            accuracy = 100
            if len(parts) >= 3:
                try:
                    accuracy = int(parts[2])
                except ValueError:
                    pass

            if random.randint(1, 100) > accuracy:
                continue

            if recipient == "self":
                before_stage = get_stat_stage(attacker.stat_boosts, "crit")
                apply_stat_change(attacker, "crit", 1, current_turn, db)
                after_stage = get_stat_stage(attacker.stat_boosts, "crit")
                if game and game_state:
                    outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1)
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(attacker, db)}'s {format_stat_log_label('crit')} {outcome_phrase}",
                        game_state,
                        db,
                    )
            elif recipient == "target":
                for target in targets:
                    before_stage = get_stat_stage(target.stat_boosts, "crit")
                    apply_stat_change(target, "crit", 1, current_turn, db)
                    after_stage = get_stat_stage(target.stat_boosts, "crit")
                    if game and game_state:
                        outcome_phrase = format_stat_change_outcome_phrase(after_stage - before_stage, 1)
                        publish_system_log_event(
                            game.link,
                            f"{get_unit_display_name(target, db)}'s {format_stat_log_label('crit')} {outcome_phrase}",
                            game_state,
                            db,
                        )

        elif effect_type == "status":
            # Check if this status has a condition
            # Format: recipient:status:condition:condition_type:condition_value:status:status_name[:accuracy]
            if len(parts) >= 7 and parts[2] == "condition":
                condition_type = parts[3]
                condition_value = parts[4]
                if parts[5] != "status":
                    continue

                status_name = parts[6]
                accuracy = 100
                if len(parts) >= 8:
                    try:
                        accuracy = int(parts[7])
                    except ValueError:
                        pass

                if random.randint(1, 100) > accuracy:
                    continue

                if recipient == "self":
                    if matches_effect_condition(attacker, condition_type, condition_value, db):
                        # If unit is immune by type, publish an immunity log instead of attempting to apply
                        if is_status_immune_by_type(attacker, status_name, db):
                            if game and game_state:
                                label = format_status_log_label(status_name)
                                if label in {"poisoned", "badly poisoned", "burned", "frozen", "paralyzed"}:
                                    publish_system_log_event(
                                        game.link,
                                        f"{get_unit_display_name(attacker, db)} wasn't {label}",
                                        game_state,
                                        db,
                                    )
                                else:
                                    publish_system_log_event(
                                        game.link,
                                        f"{get_unit_display_name(attacker, db)} wasn't affected",
                                        game_state,
                                        db,
                                    )
                        else:
                            applied = apply_status_effect(attacker, status_name, db)
                            if applied and game and game_state:
                                publish_system_log_event(
                                    game.link,
                                    f"{get_unit_display_name(attacker, db)} was {format_status_log_label(status_name)}",
                                    game_state,
                                    db,
                                )
                elif recipient == "target":
                    for target in targets:
                        if (target.current_hp or 0) <= 0:
                            continue
                        if matches_effect_condition(target, condition_type, condition_value, db):
                            # Check for Safeguard on the target
                            target_state = normalize_states(target.states)
                            if target_state and target_state[0] == "safeguard" and int(target_state[1]) > 0:
                                if game and game_state:
                                    publish_system_log_event(
                                        game.link,
                                        f"{get_unit_display_name(target, db)} is protected by Safeguard",
                                        game_state,
                                        db,
                                    )
                                continue
                            # Check for type immunity first
                            if is_status_immune_by_type(target, status_name, db):
                                if game and game_state:
                                    label = format_status_log_label(status_name)
                                    if label in {"poisoned", "badly poisoned", "burned", "frozen", "paralyzed"}:
                                        publish_system_log_event(
                                            game.link,
                                            f"{get_unit_display_name(target, db)} wasn't {label}",
                                            game_state,
                                            db,
                                        )
                                    else:
                                        publish_system_log_event(
                                            game.link,
                                            f"{get_unit_display_name(target, db)} wasn't affected",
                                            game_state,
                                            db,
                                        )
                            else:
                                applied = apply_status_effect(target, status_name, db)
                                if applied and game and game_state:
                                    publish_system_log_event(
                                        game.link,
                                        f"{get_unit_display_name(target, db)} was {format_status_log_label(status_name)}",
                                        game_state,
                                        db,
                                    )
            else:
                # Plain status effect without condition
                if len(parts) < 3:
                    continue

                status_name = parts[2]
                accuracy = 100
                if len(parts) >= 4:
                    try:
                        accuracy = int(parts[3])
                    except ValueError:
                        pass

                if random.randint(1, 100) > accuracy:
                    continue

                if recipient == "self":
                    # If attacker is immune by type, log immunity message instead of applying
                    if is_status_immune_by_type(attacker, status_name, db):
                        if game and game_state:
                            label = format_status_log_label(status_name)
                            if label in {"poisoned", "badly poisoned", "burned", "frozen", "paralyzed"}:
                                publish_system_log_event(
                                    game.link,
                                    f"{get_unit_display_name(attacker, db)} wasn't {label}",
                                    game_state,
                                    db,
                                )
                            else:
                                publish_system_log_event(
                                    game.link,
                                    f"{get_unit_display_name(attacker, db)} wasn't affected",
                                    game_state,
                                    db,
                                )
                    else:
                        applied = apply_status_effect(attacker, status_name, db)
                        if applied and game and game_state:
                            publish_system_log_event(
                                game.link,
                                f"{get_unit_display_name(attacker, db)} was {format_status_log_label(status_name)}",
                                game_state,
                                db,
                            )
                elif recipient == "target":
                    for target in targets:
                        if (target.current_hp or 0) > 0:
                            # Check for Safeguard on the target
                            target_state = normalize_states(target.states)
                            if target_state and target_state[0] == "safeguard" and int(target_state[1]) > 0:
                                if game and game_state:
                                    publish_system_log_event(
                                        game.link,
                                        f"{get_unit_display_name(target, db)} is protected by Safeguard",
                                        game_state,
                                        db,
                                    )
                                continue
                            # Check for type immunity before attempting to apply
                            if is_status_immune_by_type(target, status_name, db):
                                if game and game_state:
                                    label = format_status_log_label(status_name)
                                    if label in {"poisoned", "badly poisoned", "burned", "frozen", "paralyzed"}:
                                        publish_system_log_event(
                                            game.link,
                                            f"{get_unit_display_name(target, db)} wasn't {label}",
                                            game_state,
                                            db,
                                        )
                                    else:
                                        publish_system_log_event(
                                            game.link,
                                            f"{get_unit_display_name(target, db)} wasn't affected",
                                            game_state,
                                            db,
                                        )
                            else:
                                applied = apply_status_effect(target, status_name, db)
                                if applied and game and game_state:
                                    publish_system_log_event(
                                        game.link,
                                        f"{get_unit_display_name(target, db)} was {format_status_log_label(status_name)}",
                                        game_state,
                                        db,
                                    )

        elif effect_type == "safeguard":
            # Format: recipient:safeguard[:accuracy]
            accuracy = 100
            if len(parts) >= 3:
                try:
                    accuracy = int(parts[2])
                except ValueError:
                    pass

            if random.randint(1, 100) > accuracy:
                continue

            if recipient == "self":
                applied = apply_state_effect(attacker, "safeguard", db)
                if applied and game and game_state:
                    publish_system_log_event(
                        game.link,
                        format_state_log_message(attacker, "safeguard", db),
                        game_state,
                        db,
                    )
            elif recipient == "target":
                for target in targets:
                    if (target.current_hp or 0) <= 0:
                        continue
                    applied = apply_state_effect(target, "safeguard", db)
                    if applied and game and game_state:
                        publish_system_log_event(
                            game.link,
                            format_state_log_message(target, "safeguard", db),
                            game_state,
                            db,
                        )

        elif effect_type in {"state", "apply_state"}:
            if len(parts) < 3:
                continue

            state_name = parts[2]
            accuracy = 100
            condition_type = None
            condition_value = None

            if state_name == "condition" and len(parts) >= 6:
                condition_type = parts[3]
                condition_value = parts[4]
                state_name = parts[5]
                if len(parts) >= 7:
                    try:
                        accuracy = int(parts[6])
                    except ValueError:
                        pass
            elif len(parts) >= 4:
                try:
                    accuracy = int(parts[3])
                except ValueError:
                    pass

            if random.randint(1, 100) > accuracy:
                continue

            if recipient == "self":
                if condition_type and not matches_effect_condition(attacker, condition_type, condition_value, db):
                    continue
                applied = apply_state_effect(attacker, state_name, db)
                if applied and game and game_state:
                    publish_system_log_event(
                        game.link,
                        format_state_log_message(attacker, state_name, db),
                        game_state,
                        db,
                    )
            elif recipient == "target":
                normalized_state_name = str(state_name).lower()

                if normalized_state_name in SIDE_SCREEN_STATE_NAMES:
                    attacker_user_id = getattr(attacker, "user_id", None)
                    for target in targets:
                        if (target.current_hp or 0) <= 0:
                            continue
                        if target.user_id != attacker_user_id:
                            continue

                        applied = apply_state_effect(target, normalized_state_name, db)
                        if applied and game and game_state:
                            publish_system_log_event(
                                game.link,
                                format_state_log_message(target, normalized_state_name, db),
                                game_state,
                                db,
                            )
                    continue

                for target in targets:
                    if (target.current_hp or 0) <= 0:
                        continue

                    if condition_type and not matches_effect_condition(target, condition_type, condition_value, db):
                        continue

                    # Prevent confusion from being applied to Safeguard-protected targets
                    if normalized_state_name == "confusion":
                        target_state = normalize_states(target.states)
                        if target_state and target_state[0] == "safeguard" and int(target_state[1]) > 0:
                            if game and game_state:
                                publish_system_log_event(
                                    game.link,
                                    f"{get_unit_display_name(target, db)} is protected by Safeguard",
                                    game_state,
                                    db,
                                )
                            continue

                    # Special handling for Encore: lock target into its last used move for 2-6 turns
                    if str(state_name).lower() == "encore":
                        # Determine the target's last used move by scanning the replay log
                        last_move_id = None
                        last_move_name = None
                        if game_state and isinstance(game_state.replay_log, list):
                            for entry in reversed(game_state.replay_log or []):
                                if not isinstance(entry, dict):
                                    continue
                                if entry.get("event") != "system_log":
                                    continue
                                msg = str(entry.get("message") or "")
                                prefix = f"{get_unit_display_name(target, db)} used "
                                if msg.startswith(prefix):
                                    last_move_name = msg[len(prefix) :]
                                    break

                        if last_move_name:
                            mv = db.query(Move).filter(Move.name == last_move_name).first()
                            if mv:
                                duration = random.randint(2, 6)
                                # Preserve existing state prevention logic
                                current_state = normalize_states(target.states)
                                has_active_state = len(current_state) == 2 and int(current_state[1]) > 0
                                if not has_active_state:
                                    # Store the move id as a third element so we can enforce it on execute
                                    target.states = ["encore", duration, int(mv.id)]
                                    db.add(target)
                                    if game and game_state:
                                        publish_system_log_event(
                                            game.link,
                                            f"{get_unit_display_name(target, db)} is locked into {mv.name} for {duration} turns",
                                            game_state,
                                            db,
                                        )
                                    continue

                        # If we couldn't determine a last move, treat as unsuccessful
                        if game and game_state:
                            publish_system_log_event(
                                game.link,
                                f"{get_unit_display_name(target, db)} was unaffected",
                                game_state,
                                db,
                            )
                        continue

                    applied = apply_state_effect(target, state_name, db)
                    if applied and game and game_state:
                        publish_system_log_event(
                            game.link,
                            format_state_log_message(target, state_name, db),
                            game_state,
                            db,
                        )

        elif effect_type == "copy_ability":
            if len(parts) < 3:
                continue

            source_ref = parts[2]
            if source_ref == "target":
                if not targets:
                    continue
                source_unit = targets[0]
            elif source_ref == "self":
                source_unit = attacker
            else:
                continue

            if is_ability_suppressed(source_unit):
                continue

            source_ability_id = get_unit_ability_id(source_unit)
            if source_ability_id is None:
                continue

            recipients: list[GameUnit] = []
            if recipient == "self":
                recipients = [attacker]
            elif recipient == "target":
                recipients = [target for target in targets if (target.current_hp or 0) > 0]
            elif recipient == "ally":
                game_id = getattr(attacker, "game_id", None)
                user_id = getattr(attacker, "user_id", None)
                if not isinstance(game_id, int) or not isinstance(user_id, int):
                    continue
                try:
                    ally_units = (
                        db.query(GameUnit)
                        .filter(GameUnit.game_id == game_id, GameUnit.user_id == user_id)
                        .all()
                    )
                except Exception:
                    ally_units = []
                map_obj_local = None
                if game is not None:
                    map_obj_local = db.query(Map).filter_by(id=game.map_id).first()
                if map_obj_local is None:
                    continue
                width = int(getattr(map_obj_local, "width", 0) or 0)
                height = int(getattr(map_obj_local, "height", 0) or 0)
                tile_set = set(get_move_affected_tiles(move, attacker, width, height))
                recipients = [
                    ally
                    for ally in ally_units
                    if (ally.current_hp or 0) > 0
                    and (int(ally.current_x), int(ally.current_y)) in tile_set
                ]

            for unit in recipients:
                set_unit_ability_id(unit, source_ability_id, db)
                attach_game_unit_loadout_fields(unit, db)
                if game and game_state:
                    ability_name = resolve_ability_name(source_ability_id, db) or "ability"
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(unit, db)} copied {ability_name}",
                        game_state,
                        db,
                    )

        elif effect_type == "defog":
            # Clear reflect/light_screen from target's side (target:defog)
            if recipient == "target":
                for target in targets:
                    try:
                        side_units = (
                            db.query(GameUnit)
                            .filter(GameUnit.game_id == target.game_id, GameUnit.user_id == target.user_id)
                            .all()
                        )
                    except Exception:
                        side_units = []

                    for u in side_units:
                        s = normalize_states(u.states)
                        if s and s[0] in {"reflect", "light_screen", "aurora_veil"}:
                            removed_state = s[0]
                            u.states = []
                            db.add(u)
                            if game and game_state:
                                publish_system_log_event(
                                    game.link,
                                    f"{get_unit_display_name(u, db)} lost {removed_state.replace('_', ' ')}",
                                    game_state,
                                    db,
                                )

            elif effect_type == "destiny_bond":
                # Format: recipient:destiny_bond[:accuracy]
                accuracy = 100
                if len(parts) >= 3:
                    try:
                        accuracy = int(parts[2])
                    except ValueError:
                        pass

                if random.randint(1, 100) > accuracy:
                    continue

                if recipient == "self":
                    applied = apply_state_effect(attacker, "destiny_bond", db)
                    if applied and game and game_state:
                        publish_system_log_event(
                            game.link,
                            format_state_log_message(attacker, "destiny_bond", db),
                            game_state,
                            db,
                        )
                elif recipient == "target":
                    for target in targets:
                        if (target.current_hp or 0) <= 0:
                            continue
                        applied = apply_state_effect(target, "destiny_bond", db)
                        if applied and game and game_state:
                            publish_system_log_event(
                                game.link,
                                format_state_log_message(target, "destiny_bond", db),
                                game_state,
                                db,
                            )
            elif effect_type == "laser_focus":
                # Format: recipient:laser_focus[:accuracy]
                accuracy = 100
                if len(parts) >= 3:
                    try:
                        accuracy = int(parts[2])
                    except ValueError:
                        pass

                if random.randint(1, 100) > accuracy:
                    continue

                if recipient == "self":
                    applied = apply_state_effect(attacker, "laser_focus", db)
                    if applied and game and game_state:
                        publish_system_log_event(
                            game.link,
                            format_state_log_message(attacker, "laser_focus", db),
                            game_state,
                            db,
                        )
                elif recipient == "target":
                    for target in targets:
                        if (target.current_hp or 0) <= 0:
                            continue
                        applied = apply_state_effect(target, "laser_focus", db)
                        if applied and game and game_state:
                            publish_system_log_event(
                                game.link,
                                format_state_log_message(target, "laser_focus", db),
                                game_state,
                                db,
                            )

        elif effect_type == "heal":
            # Check if this heal has a condition
            # Format: recipient:heal:condition:condition_type:condition_value:denominator
            if len(parts) >= 6 and parts[2] == "condition":
                condition_type = parts[3]
                condition_value = parts[4]
                try:
                    denominator = int(parts[5])
                    if denominator <= 0:
                        continue
                except ValueError:
                    continue

                # For conditional healing based on weather
                if condition_type.lower() == "weather":
                    # Determine weather_id for attacker or target
                    if recipient == "self":
                        weather_id = get_unit_weather_id(attacker, weather_tiles)
                    else:
                        # For target healing, use first target's weather
                        if not targets:
                            continue
                        weather_id = get_unit_weather_id(targets[0], weather_tiles)

                    # Check if condition matches
                    if not weather_condition_matches(weather_id, condition_value):
                        continue

                    # Apply the conditional heal
                    if recipient == "self":
                        max_hp = (attacker.current_stats or {}).get("hp", 1)
                        heal_amount = max(1, max_hp // denominator)
                        old_hp = attacker.current_hp or 0
                        # Check for Heal Block on attacker
                        att_state = normalize_states(attacker.states)
                        if att_state and att_state[0] == "heal_block" and int(att_state[1]) > 0:
                            if game and game_state:
                                publish_system_log_event(game.link, f"{get_unit_display_name(attacker, db)} can't be healed due to Heal Block", game_state, db)
                        else:
                            attacker.current_hp = min(max_hp, old_hp + heal_amount)
                            restored_hp = max(0, int(attacker.current_hp or 0) - int(old_hp or 0))
                            db.add(attacker)
                            if restored_hp > 0 and game and game_state:
                                publish_system_log_event(game.link, f"{get_unit_display_name(attacker, db)} regained {restored_hp} health", game_state, db)
                    elif recipient == "target":
                        for target in targets:
                            if (target.current_hp or 0) > 0:
                                # Check for Heal Block on target
                                t_state = normalize_states(target.states)
                                if t_state and t_state[0] == "heal_block" and int(t_state[1]) > 0:
                                    if game and game_state:
                                        publish_system_log_event(game.link, f"{get_unit_display_name(target, db)} can't be healed due to Heal Block", game_state, db)
                                    continue
                                max_hp = (target.current_stats or {}).get("hp", 1)
                                heal_amount = max(1, max_hp // denominator)
                                old_hp = target.current_hp or 0
                                target.current_hp = min(max_hp, old_hp + heal_amount)
                                restored_hp = max(0, int(target.current_hp or 0) - int(old_hp or 0))
                                db.add(target)
                                if restored_hp > 0 and game and game_state:
                                    publish_system_log_event(game.link, f"{get_unit_display_name(target, db)} regained {restored_hp} health", game_state, db)
            else:
                # Plain heal effect without condition
                if len(parts) < 3:
                    continue

                try:
                    denominator = int(parts[2])
                    if denominator <= 0:
                        continue
                except ValueError:
                    continue

                if recipient == "self":
                    # Get max HP from attacker's current_stats
                    max_hp = (attacker.current_stats or {}).get("hp", 1)
                    heal_amount = max(1, max_hp // denominator)
                    old_hp = attacker.current_hp or 0
                    attacker.current_hp = min(max_hp, old_hp + heal_amount)
                    restored_hp = max(0, int(attacker.current_hp or 0) - int(old_hp or 0))
                    db.add(attacker)
                    if restored_hp > 0 and game and game_state:
                        publish_system_log_event(game.link, f"{get_unit_display_name(attacker, db)} regained {restored_hp} health", game_state, db)
                elif recipient == "target":
                    for target in targets:
                        # Only heal if target is alive
                        if (target.current_hp or 0) > 0:
                            max_hp = (target.current_stats or {}).get("hp", 1)
                            heal_amount = max(1, max_hp // denominator)
                            old_hp = target.current_hp or 0
                            target.current_hp = min(max_hp, old_hp + heal_amount)
                            restored_hp = max(0, int(target.current_hp or 0) - int(old_hp or 0))
                            db.add(target)
                            if restored_hp > 0 and game and game_state:
                                publish_system_log_event(game.link, f"{get_unit_display_name(target, db)} regained {restored_hp} health", game_state, db)

        elif effect_type == "cure_status":
            if len(parts) < 3:
                continue

            status_spec = parts[2]
            if recipient == "self":
                cure_status_effect(attacker, status_spec, db)
            elif recipient == "target":
                for target in targets:
                    if (target.current_hp or 0) > 0:
                        cure_status_effect(target, status_spec, db)

        elif effect_type == "reset_stats":
            if recipient == "self":
                attacker.stat_boosts = default_stat_boosts()
                attacker.current_stats = compute_effective_stats(attacker, db)
                db.add(attacker)
            elif recipient == "target":
                for target in targets:
                    target.stat_boosts = default_stat_boosts()
                    target.current_stats = compute_effective_stats(target, db)
                    db.add(target)

        elif effect_type == "give_cash":
            if len(parts) < 3 or recipient != "target":
                continue
            try:
                cash_amount = int(parts[2])
            except ValueError:
                continue
            if cash_amount <= 0:
                continue

            for target in targets:
                player_state = (
                    db.query(GamePlayer)
                    .filter_by(game_id=target.game_id, player_id=target.user_id)
                    .first()
                )
                if player_state is None:
                    continue
                player_state.cash_remaining = int(player_state.cash_remaining or 0) + cash_amount
                db.add(player_state)
                if game and game_state:
                    username = get_username_by_id(target.user_id, db)
                    publish_system_log_event(
                        game.link,
                        f"{username} received {cash_amount} money",
                        game_state,
                        db,
                    )

        elif effect_type == "revive":
            if len(parts) < 3 or recipient != "target":
                continue
            try:
                hp_denominator = int(parts[2])
                if hp_denominator <= 0:
                    continue
            except ValueError:
                continue

            att_state = normalize_states(attacker.states)
            if att_state and att_state[0] == "heal_block" and int(att_state[1]) > 0:
                if game and game_state:
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(attacker, db)} can't heal due to Heal Block",
                        game_state,
                        db,
                    )
                continue

            map_obj = db.query(Map).filter_by(id=game.map_id).first() if game else None
            if map_obj is None:
                continue

            for target in targets:
                if not target.is_fainted and int(target.current_hp or 0) > 0:
                    continue
                if target.user_id != attacker.user_id:
                    continue

                placement = find_revival_placement_tile(attacker, map_obj, db)
                if placement is None:
                    if game and game_state:
                        publish_system_log_event(
                            game.link,
                            f"{get_unit_display_name(target, db)} couldn't be revived",
                            game_state,
                            db,
                        )
                    continue

                max_hp = int((target.current_stats or {}).get("hp", 1) or 1)
                restored_hp = max(1, max_hp // hp_denominator)
                target.is_fainted = False
                target.current_hp = restored_hp
                target.can_move = True
                target.current_x, target.current_y = placement
                target.starting_x, target.starting_y = placement
                target.current_stats = compute_effective_stats(target, db)
                db.add(target)

                player_state = (
                    db.query(GamePlayer)
                    .filter_by(game_id=target.game_id, player_id=target.user_id)
                    .first()
                )
                if player_state is not None and target.id not in (player_state.game_units or []):
                    player_state.game_units = list(player_state.game_units or []) + [target.id]
                    db.add(player_state)

                if game and game_state:
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(target, db)} was revived with {restored_hp} HP",
                        game_state,
                        db,
                    )

        elif effect_type == "instant_ko":
            if recipient == "self":
                if (attacker.current_hp or 0) > 0:
                    attacker.current_hp = 0
                    db.add(attacker)
            elif recipient == "target":
                for target in targets:
                    if (target.current_hp or 0) > 0:
                        target.current_hp = 0
                        db.add(target)


def apply_damage_based_move_effects(
    move: Move,
    attacker: GameUnit,
    targets: List[GameUnit],
    damage_results: List[dict],
    db: Session,
    game: "Game | None" = None,
    game_state: "GameState | None" = None,
    faint_logged_ids: set[int] | None = None,
) -> List[int]:
    """
    Apply effects that scale from total direct damage dealt by this move.
    Supported effect formats:
    - self:drain:num
    - self:recoil:damage_dealt:num
    - self:recoil:maximum_hp:num
    - target:drain:num
    - target:recoil:damage_dealt:num
    - target:recoil:maximum_hp:num
    Drain amount is floor(total_damage_dealt / num).
    """
    if not move.effects:
        return []

    total_damage_dealt = sum(max(0, int(result.get("damage", 0) or 0)) for result in damage_results)

    fainted_unit_ids: set[int] = set()

    def apply_to_unit(unit: GameUnit, effect_type: str, amount: int):
        if amount <= 0 or (unit.current_hp or 0) <= 0:
            return

        if effect_type == "drain":
            max_hp = (unit.current_stats or {}).get("hp", unit.current_hp or 0)
            if max_hp <= 0:
                return
            unit.current_hp = min(max_hp, (unit.current_hp or 0) + amount)
            db.add(unit)
        elif effect_type == "recoil":
            damage_taken = min(amount, int(unit.current_hp or 0))
            unit.current_hp = max(0, (unit.current_hp or 0) - amount)
            if damage_taken > 0 and game and game_state:
                publish_system_log_event(
                    game.link,
                    f"{get_unit_display_name(unit, db)} took {damage_taken} damage as recoil",
                    game_state,
                    db,
                )
            if unit.current_hp <= 0:
                fainted_unit_ids.add(unit.id)
                if game and game_state and (faint_logged_ids is None or unit.id not in faint_logged_ids):
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(unit, db)} fainted!",
                        game_state,
                        db,
                    )
                    if faint_logged_ids is not None:
                        faint_logged_ids.add(unit.id)
            db.add(unit)

    for effect_str in move.effects:
        parts = effect_str.split(":")
        if len(parts) < 2:
            continue
        recipient = parts[0]
        effect_type = parts[1]
        if effect_type not in {"drain", "recoil"}:
            continue

        if effect_type == "drain":
            if len(parts) != 3:
                continue
            try:
                denominator = int(parts[2])
                if denominator <= 0:
                    continue
            except ValueError:
                continue

            effect_amount = total_damage_dealt // denominator
            if effect_amount <= 0:
                continue

            if recipient == "self":
                apply_to_unit(attacker, effect_type, effect_amount)
            elif recipient == "target":
                for target in targets:
                    apply_to_unit(target, effect_type, effect_amount)
            continue

        # Recoil format: recipient:recoil:damage_dealt|maximum_hp:num
        if len(parts) != 4:
            continue

        recoil_basis = parts[2]
        try:
            denominator = int(parts[3])
            if denominator <= 0:
                continue
        except ValueError:
            continue

        recipients = [attacker] if recipient == "self" else (targets if recipient == "target" else [])
        if not recipients:
            continue

        for unit in recipients:
            if recoil_basis == "damage_dealt":
                effect_amount = total_damage_dealt // denominator
            elif recoil_basis == "maximum_hp":
                max_hp = (unit.current_stats or {}).get("hp", unit.current_hp or 0)
                if max_hp <= 0:
                    continue
                effect_amount = max_hp // denominator
            else:
                continue

            if effect_amount <= 0:
                continue

            apply_to_unit(unit, effect_type, effect_amount)

    # Keep response payload synchronized if a target's HP changed from a target-based recoil/drain.
    if damage_results:
        hp_by_id = {target.id: target.current_hp for target in targets}
        for result in damage_results:
            target_id = result.get("id")
            if target_id in hp_by_id:
                result["current_hp"] = hp_by_id[target_id]

    return list(fainted_unit_ids)


def move_deals_direct_damage(move: Move) -> bool:
    if move_has_target_fixed_damage_effect(move):
        return True

    category = (move.category or "").lower()
    power = move.power or 0
    return category in {"physical", "special"} and power > 0


def move_can_critical_hit(move: Move) -> bool:
    """Return whether this move is eligible to roll critical hits."""
    if move_has_effect_token(move, "guaranteed_crit"):
        return True
    if move_has_target_fixed_damage_effect(move):
        return False

    category = (move.category or "").lower()
    power = move.power or 0
    return category in {"physical", "special"} and power > 0

def decrement_and_expire_stat_boosts(user_id: int, game_id: int, db: Session) -> list[int]:
    """
    Decrement stat boost timers for a player's units and remove expired ones.
    Returns list of unit IDs that had their stat boosts modified.
    """
    units = db.query(GameUnit).filter(
        GameUnit.game_id == game_id,
        GameUnit.user_id == user_id
    ).all()
    
    modified_unit_ids = []
    
    for unit in units:
        unit.stat_boosts = normalize_stat_boosts(unit.stat_boosts)
        
        modified = False
        for stat, instances in unit.stat_boosts.items():
            if not isinstance(instances, list):
                continue
            
            # Decrement expires_turn for each instance
            for inst in instances:
                if "expires_turn" in inst:
                    inst["expires_turn"] -= 1
                    modified = True
            
            # Filter out instances that reached 0 or below
            original_count = len(instances)
            unit.stat_boosts[stat] = [
                inst for inst in instances 
                if inst.get("expires_turn", 0) > 0
            ]
            
            if len(unit.stat_boosts[stat]) != original_count:
                modified = True
        
        if modified:
            # Mark as modified for SQLAlchemy
            unit.stat_boosts = dict(unit.stat_boosts)
            # Recalculate current_stats to reflect the new stat boosts
            unit.current_stats = compute_effective_stats(unit, db)
            db.add(unit)
            modified_unit_ids.append(unit.id)
    
    return modified_unit_ids


def decrement_and_expire_status_effects(
    user_id: int,
    game_id: int,
    db: Session,
    game: Game | None = None,
    game_state: GameState | None = None,
) -> list[int]:
    """
    Decrement status timers for a player's units and remove expired statuses.
    Status checks that affect movement are resolved at turn start.
    Returns list of unit IDs that had their status effects modified.
    """
    units = db.query(GameUnit).filter(
        GameUnit.game_id == game_id,
        GameUnit.user_id == user_id
    ).all()

    modified_unit_ids = []

    for unit in units:
        # Turn-start baseline: units can act unless an active status blocks movement.
        if not unit.can_move:
            unit.can_move = True
            db.add(unit)
            modified_unit_ids.append(unit.id)

        status_effect = normalize_status_effects(unit.status_effects)
        if not status_effect:
            if unit.status_effects:
                unit.status_effects = []
                unit.current_stats = compute_effective_stats(unit, db)
                db.add(unit)
                modified_unit_ids.append(unit.id)
        else:
            status_name = status_effect[0]
            turns_remaining = int(status_effect[1]) - 1

            # Expire first; if cured this turn, skip status-specific effects.
            if turns_remaining <= 0:
                unit.status_effects = []
                unit.current_stats = compute_effective_stats(unit, db)
                db.add(unit)
                # If sleep expired, also clear Nightmare state if present
                s = normalize_states(unit.states)
                if s and s[0] == "nightmare":
                    unit.states = []
                    db.add(unit)
                    if game and game_state:
                        publish_system_log_event(
                            game.link,
                            f"{get_unit_display_name(unit, db)} is no longer haunted by nightmares",
                            game_state,
                            db,
                        )
                modified_unit_ids.append(unit.id)
            else:
                if status_name == "sleep":
                    unit.can_move = False
                elif status_name == "frozen":
                    unit.can_move = False
                elif status_name == "paralysis":
                    if random.randint(1, 100) <= 25:
                        unit.can_move = False

                if status_name == "badly_poisoned":
                    bad_poison_turn = int(status_effect[2]) if len(status_effect) >= 3 else 1
                    unit.status_effects = [status_name, turns_remaining, max(1, bad_poison_turn)]
                else:
                    unit.status_effects = [status_name, turns_remaining]

                unit.current_stats = compute_effective_stats(unit, db)
        state_effect = normalize_states(unit.states)
        if state_effect:
            state_name = str(state_effect[0]).lower()
            state_turns_remaining = int(state_effect[1]) - 1
            if state_turns_remaining <= 0:
                if state_name == "flinch":
                    unit.can_move = False
                unit.states = []
                db.add(unit)
                if state_name == "confusion" and game and game_state:
                    publish_system_log_event(
                        game.link,
                        f"{get_unit_display_name(unit, db)} is no longer confused",
                        game_state,
                        db,
                    )
                if state_name == "drowsy":
                    # Drowsy expired: attempt to put the unit to sleep after two rounds.
                    # If the unit already has a status, do not apply sleep.
                    current_status = normalize_status_effects(unit.status_effects)
                    if not current_status:
                        applied = apply_status_effect(unit, "sleep", db)
                        if applied and game and game_state:
                            publish_system_log_event(
                                game.link,
                                f"{get_unit_display_name(unit, db)} was {format_status_log_label('sleep')}",
                                game_state,
                                db,
                            )
                modified_unit_ids.append(unit.id)
                continue

            # Preserve any extra stored metadata for certain states (e.g., Encore stores the locked move id at index 2)
            raw_state = unit.states if isinstance(unit.states, list) else []
            if isinstance(raw_state, list) and len(raw_state) >= 3 and str(raw_state[0]).lower() == state_name:
                extra = raw_state[2]
                unit.states = [state_name, state_turns_remaining, extra]
            else:
                unit.states = [state_name, state_turns_remaining]
            if state_name == "confusion" and unit.can_move and random.randint(1, 100) <= 33:
                apply_confusion_self_damage(unit, db, game, game_state)
                unit.can_move = False
            elif state_name == "flinch":
                unit.can_move = False
            elif state_name == "ingrain":
                unit.can_move = False

        db.add(unit)
        modified_unit_ids.append(unit.id)

    return modified_unit_ids


def decrement_and_expire_hazards(game_id: int, db: Session) -> bool:
    """Decrement duration for all active hazard stacks and remove expired stacks."""
    map_state = db.query(GameMapState).filter(GameMapState.game_id == game_id).first()
    if not map_state or not isinstance(map_state.hazard_tiles, list):
        return False

    changed = False
    next_grid: list[list[list[list[int]]]] = []

    for row in map_state.hazard_tiles:
        if not isinstance(row, list):
            next_grid.append([])
            changed = True
            continue

        next_row: list[list[list[int]]] = []
        for cell in row:
            normalized_entries = normalize_hazard_cell(cell)
            next_entries: list[list[int]] = []

            if normalized_entries != cell:
                changed = True

            for hazard_id, turns_remaining in normalized_entries:
                next_turns = int(turns_remaining) - 1
                if next_turns > 0:
                    next_entries.append([int(hazard_id), next_turns])
                else:
                    changed = True

            next_row.append(next_entries)

            if next_entries != normalized_entries:
                changed = True

        next_grid.append(next_row)

    if changed:
        map_state.hazard_tiles = next_grid
        db.add(map_state)

    return changed


def apply_end_of_turn_status_damage(user_id: int, game_id: int, db: Session) -> list[int]:
    """
    Apply end-of-turn status damage for a player's units.
    Duration decrement is handled at turn start; this function only applies damage.
    Returns list of unit IDs that had HP/status values modified.
    """
    units = db.query(GameUnit).filter(
        GameUnit.game_id == game_id,
        GameUnit.user_id == user_id
    ).all()

    modified_unit_ids = []
    game = db.query(Game).filter(Game.id == game_id).first()
    game_state = db.query(GameState).filter(GameState.game_id == game_id).first()

    for unit in units:
        status_effect = normalize_status_effects(unit.status_effects)
        max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
        current_hp = int(unit.current_hp or 0)
        hp_after_effects = current_hp
        modified = False

        if status_effect:
            status_name = status_effect[0]

            if status_name in {"burn", "poison"}:
                damage = max(1, max_hp // 8) if max_hp > 0 else 0
                hp_after_effects = max(0, hp_after_effects - damage)
                modified = modified or damage > 0
                if damage > 0 and game:
                    unit_name = get_unit_display_name(unit, db)
                    publish_system_log_event(game.link, f"{unit_name} took {damage} damage from {status_name}", game_state, db)
            elif status_name == "badly_poisoned":
                bad_poison_turn = int(status_effect[2]) if len(status_effect) >= 3 else 1
                bad_poison_turn = max(1, bad_poison_turn)
                damage = max(1, (max_hp * bad_poison_turn) // 16) if max_hp > 0 else 0
                hp_after_effects = max(0, hp_after_effects - damage)
                unit.status_effects = [status_name, int(status_effect[1]), bad_poison_turn + 1]
                modified = True
                if damage > 0 and game:
                    unit_name = get_unit_display_name(unit, db)
                    publish_system_log_event(game.link, f"{unit_name} took {damage} from badly poisoned", game_state, db)

        if hp_after_effects != current_hp:
            unit.current_hp = hp_after_effects
            modified = True

        if modified:
            db.add(unit)
            modified_unit_ids.append(unit.id)

    return modified_unit_ids


def apply_end_of_round_weather_damage(game_id: int, db: Session) -> list[int]:
    """
    Apply weather chip damage once per full round, after the last player finishes.
    Returns list of unit IDs whose HP changed.
    """
    map_state = db.query(GameMapState).filter(GameMapState.game_id == game_id).first()
    weather_tiles = map_state.weather_tiles if map_state and isinstance(map_state.weather_tiles, list) else None

    game = db.query(Game).filter(Game.id == game_id).first()
    game_state = db.query(GameState).filter(GameState.game_id == game_id).first()
    units = db.query(GameUnit).filter(GameUnit.game_id == game_id).all()
    modified_unit_ids = []

    for unit in units:
        max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
        current_hp = int(unit.current_hp or 0)
        if current_hp <= 0:
            continue

        weather_id = get_unit_weather_id(unit, weather_tiles)
        unit_types = get_unit_types(unit, db)
        damage = 0

        if weather_id == WEATHER_TO_ID["sandstorm"] and not unit_types.intersection({"rock", "ground", "steel"}):
            damage = max(1, max_hp // 16) if max_hp > 0 else 0
            if damage > 0 and game:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(game.link, f"{unit_name} took {damage} damage from the sandstorm", game_state, db)
        elif weather_id == WEATHER_TO_ID["hail"] and "ice" not in unit_types:
            damage = max(1, max_hp // 16) if max_hp > 0 else 0
            if damage > 0 and game:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(game.link, f"{unit_name} took {damage} damage from hail", game_state, db)

        if damage <= 0:
            continue

        unit.current_hp = max(0, current_hp - damage)
        db.add(unit)
        modified_unit_ids.append(unit.id)

    # Apply Aqua Ring healing at end of round for units that have the state
    for unit in units:
        if int(unit.current_hp or 0) <= 0:
            continue
        state_effect = normalize_states(unit.states)
        if not state_effect:
            continue
        if state_effect[0] == "aqua_ring" or state_effect[0] == "ingrain":
            max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
            if max_hp <= 0:
                continue
            if state_effect[0] == "aqua_ring":
                heal = max(1, max_hp // 16)
                tag = "Aqua Ring"
            else:
                heal = max(1, max_hp // 8)
                tag = "Ingrain"
            # Check for Heal Block before applying end-of-round heals
            s_check = normalize_states(unit.states)
            if s_check and s_check[0] == "heal_block" and int(s_check[1]) > 0:
                if game and game_state:
                    unit_name = get_unit_display_name(unit, db)
                    publish_system_log_event(game.link, f"{unit_name} can't be healed due to Heal Block", game_state, db)
                continue
            before_hp = int(unit.current_hp or 0)
            unit.current_hp = min(max_hp, before_hp + heal)
            db.add(unit)
            modified_unit_ids.append(unit.id)
            if game and game_state:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(game.link, f"{unit_name} healed {heal} HP from {tag}", game_state, db)
        elif state_effect[0] == "cursed":
            # Apply Cursed damage at end of round: lose 1/4 max HP
            max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
            if max_hp <= 0:
                continue
            damage = max(1, max_hp // 4)
            before_hp = int(unit.current_hp or 0)
            if before_hp <= 0:
                continue
            unit.current_hp = max(0, before_hp - damage)
            db.add(unit)
            modified_unit_ids.append(unit.id)
            if game and game_state:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(game.link, f"{unit_name} took {damage} damage from Curse", game_state, db)
        elif state_effect[0] == "nightmare":
            # Nightmare deals damage only if the unit is asleep
            status = normalize_status_effects(unit.status_effects)
            if not status or status[0] != "sleep" or int(status[1]) <= 0:
                continue
            max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
            if max_hp <= 0:
                continue
            damage = max(1, max_hp // 4)
            before_hp = int(unit.current_hp or 0)
            if before_hp <= 0:
                continue
            unit.current_hp = max(0, before_hp - damage)
            db.add(unit)
            modified_unit_ids.append(unit.id)
            if game and game_state:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(game.link, f"{unit_name} took {damage} damage from Nightmare", game_state, db)
        elif state_effect[0] == "salt_cure":
            # Salt Cure deals 1/16 max HP, or 1/8 if Steel or Water type (no stacking if both)
            unit_types = get_unit_types(unit, db)
            if "steel" in unit_types or "water" in unit_types:
                denom = 8
            else:
                denom = 16
            max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
            if max_hp <= 0:
                continue
            damage = max(1, max_hp // denom)
            before_hp = int(unit.current_hp or 0)
            if before_hp <= 0:
                continue
            unit.current_hp = max(0, before_hp - damage)
            db.add(unit)
            modified_unit_ids.append(unit.id)
            if game and game_state:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(game.link, f"{unit_name} took {damage} damage from Salt Cure", game_state, db)

    modified_unit_ids.extend(apply_end_of_round_stump_tile_effects(game_id, db))

    return modified_unit_ids


def apply_end_of_round_stump_tile_effects(game_id: int, db: Session) -> list[int]:
    """Grass-type units on stump tiles heal 1/8 max HP at end of round."""
    map_state = db.query(GameMapState).filter(GameMapState.game_id == game_id).first()
    if not map_state or not map_state.map_id:
        return []

    map_obj = db.query(Map).filter(Map.id == map_state.map_id).first()
    special_tiles = map_obj.tile_data.get("special_tiles") if map_obj and map_obj.tile_data else None
    if not special_tiles:
        return []

    game = db.query(Game).filter(Game.id == game_id).first()
    game_state = db.query(GameState).filter(GameState.game_id == game_id).first()
    units = db.query(GameUnit).filter(GameUnit.game_id == game_id).all()
    modified_unit_ids: list[int] = []

    for unit in units:
        if int(unit.current_hp or 0) <= 0:
            continue
        if "grass" not in get_unit_types(unit, db):
            continue
        unit_types = get_unit_types(unit, db)
        ability_names = get_unit_ability_names(unit, db)
        if not target_receives_grass_tile_bonuses(unit_types, ability_names):
            continue

        x = int(getattr(unit, "current_x", -1) or -1)
        y = int(getattr(unit, "current_y", -1) or -1)
        if not is_stump_tile(special_tiles, x, y):
            continue

        max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
        if max_hp <= 0:
            continue

        state_effect = normalize_states(unit.states)
        if state_effect and state_effect[0] == "heal_block" and int(state_effect[1]) > 0:
            if game and game_state:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(
                    game.link,
                    f"{unit_name} can't be healed due to Heal Block",
                    game_state,
                    db,
                )
            continue

        heal = max(1, max_hp // 8)
        before_hp = int(unit.current_hp or 0)
        unit.current_hp = min(max_hp, before_hp + heal)
        db.add(unit)
        modified_unit_ids.append(unit.id)
        if game and game_state:
            unit_name = get_unit_display_name(unit, db)
            publish_system_log_event(
                game.link,
                f"{unit_name} healed {heal} HP from the stump",
                game_state,
                db,
            )

    return modified_unit_ids


def apply_end_of_round_entry_hazard_effects(game_id: int, current_turn: int, db: Session) -> list[int]:
    """
    Apply tile entry-hazard effects once per full round, aligned with weather timing.
    Hazard behavior:
    - spikes(1): 1 stack=1/8, 2 stacks=1/6, 3+ stacks=1/4 max HP; no effect on flying.
    - toxic_spikes(2): 1 stack=poison, 2+ stacks=badly_poisoned; no effect on flying; no overwrite.
    - stealth_rock(3): (max_hp / 8) scaled by rock-type effectiveness.
    - sticky_web(4): lower speed by one stage.
    """
    map_state = db.query(GameMapState).filter(GameMapState.game_id == game_id).first()
    hazard_tiles = map_state.hazard_tiles if map_state and isinstance(map_state.hazard_tiles, list) else None
    if not isinstance(hazard_tiles, list):
        return []

    game = db.query(Game).filter(Game.id == game_id).first()
    game_state = db.query(GameState).filter(GameState.game_id == game_id).first()
    units = db.query(GameUnit).filter(GameUnit.game_id == game_id).all()
    modified_unit_ids: list[int] = []

    for unit in units:
        max_hp = int((unit.current_stats or {}).get("hp", 0) or 0)
        current_hp = int(unit.current_hp or 0)
        if current_hp <= 0:
            continue

        x = int(getattr(unit, "current_x", -1) or -1)
        y = int(getattr(unit, "current_y", -1) or -1)
        entries = get_hazard_entries_at_position(hazard_tiles, x, y)
        if not entries:
            continue

        unit_types = get_unit_types(unit, db)
        is_flying = "flying" in unit_types

        spikes_layers = sum(1 for hazard_id, _ in entries if int(hazard_id) == 1)
        toxic_spikes_layers = sum(1 for hazard_id, _ in entries if int(hazard_id) == 2)
        has_stealth_rock = any(int(hazard_id) == 3 for hazard_id, _ in entries)
        has_sticky_web = any(int(hazard_id) == 4 for hazard_id, _ in entries)

        hp_after_effects = current_hp
        modified = False

        if spikes_layers > 0 and not is_flying and max_hp > 0:
            if spikes_layers >= 3:
                damage = max(1, max_hp // 4)
            elif spikes_layers == 2:
                damage = max(1, max_hp // 6)
            else:
                damage = max(1, max_hp // 8)
            hp_after_effects = max(0, hp_after_effects - damage)
            modified = True
            if game:
                unit_name = get_unit_display_name(unit, db)
                publish_system_log_event(game.link, f"{unit_name} took {damage} damage from spikes", game_state, db)

        if has_stealth_rock and max_hp > 0:
            type_multiplier = get_type_multiplier("rock", list(unit_types))
            if type_multiplier > 0:
                rock_damage = max(1, int((max_hp * type_multiplier) // 8))
                hp_after_effects = max(0, hp_after_effects - rock_damage)
                modified = True
                if game:
                    unit_name = get_unit_display_name(unit, db)
                    publish_system_log_event(game.link, f"{unit_name} took {rock_damage} damage from floating rocks", game_state, db)

        if toxic_spikes_layers > 0 and not is_flying:
            status_to_apply = "badly_poisoned" if toxic_spikes_layers >= 2 else "poison"
            applied = apply_status_effect(unit, status_to_apply, db)
            if applied:
                modified = True
            else:
                # If the status wasn't applied because of type immunity, publish a system log so chat shows it
                if is_status_immune_by_type(unit, status_to_apply, db) and game and game_state:
                    label = format_status_log_label(status_to_apply)
                    if label in {"poisoned", "badly poisoned", "burned", "frozen", "paralyzed"}:
                        publish_system_log_event(
                            game.link,
                            f"{get_unit_display_name(unit, db)} wasn't {label}",
                            game_state,
                            db,
                        )
                    else:
                        publish_system_log_event(
                            game.link,
                            f"{get_unit_display_name(unit, db)} wasn't affected",
                            game_state,
                            db,
                        )

        if has_sticky_web:
            apply_stat_change(unit, "speed", -1, current_turn, db)
            modified = True

        if hp_after_effects != current_hp:
            unit.current_hp = hp_after_effects
            db.add(unit)

        if modified:
            modified_unit_ids.append(unit.id)

    return modified_unit_ids


def remove_fainted_units_from_play(game_id: int, db: Session) -> list[int]:
    """
    Remove all units with HP at or below 0 from active play.
    Returns removed unit IDs.
    """
    fainted_units = (
        db.query(GameUnit)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.current_hp <= 0,
            GameUnit.is_fainted == False,
        )
        .all()
    )
    if not fainted_units:
        return []

    game = db.query(Game).filter(Game.id == game_id).first()
    game_state = db.query(GameState).filter(GameState.game_id == game_id).first()

    removed_ids: list[int] = []
    for unit in fainted_units:
        if game:
            publish_system_log_event(game.link, f"{get_unit_display_name(unit, db)} fainted!", game_state, db)

        player_state = db.query(GamePlayer).filter_by(game_id=game_id, player_id=unit.user_id).first()
        if player_state and unit.id in player_state.game_units:
            player_state.game_units.remove(unit.id)
            db.add(player_state)

        faint_unit_in_place(unit, db)
        removed_ids.append(unit.id)

    active_counts = get_remaining_unit_counts(game_id, db)
    if game:
        affected_users = {unit.user_id for unit in fainted_units}
        for user_id in affected_users:
            if active_counts.get(user_id, 0) == 0:
                username = get_username_by_id(user_id, db)
                publish_system_log_event(
                    game.link,
                    f"{username} has no more units and is unable to battle!",
                    game_state,
                    db,
                )

    return removed_ids

def get_remaining_unit_counts(game_id: int, db: Session) -> dict:
    counts: dict[int, int] = {}
    units = db.query(GameUnit).filter(GameUnit.game_id == game_id).all()
    for unit in units:
        if unit.is_fainted or int(unit.current_hp or 0) <= 0:
            continue
        counts[unit.user_id] = counts.get(unit.user_id, 0) + 1
    return counts


def get_playable_player_ids_in_order(state: GameState, game_id: int, db: Session) -> List[int]:
    player_order = list(state.players or [])
    alive_player_rows = (
        db.query(GameUnit.user_id)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.is_fainted == False,
            GameUnit.current_hp > 0,
        )
        .distinct()
        .all()
    )
    alive_player_ids = {int(row[0]) for row in alive_player_rows}
    return [player_id for player_id in player_order if player_id in alive_player_ids]


def reconcile_playable_players(game: Game, state: GameState, db: Session) -> tuple[List[int], List[int], bool]:
    """
    Keep turn order synced to players that still have at least one unit in play.
    Returns (playable_player_ids, eliminated_player_ids, game_completed_now).
    """
    previous_players = list(state.players or [])

    # Only enforce elimination/playable-turn logic during active gameplay.
    # Preparation/open/closed should preserve lobby player order even with zero units placed.
    if state.status != GameStatus.in_progress:
        if state.current_turn is None:
            state.current_turn = 0
        return previous_players, [], False

    playable_players = get_playable_player_ids_in_order(state, game.id, db)
    eliminated_players = [player_id for player_id in previous_players if player_id not in playable_players]

    if playable_players != previous_players:
        state.players = playable_players

    if state.current_turn is None:
        state.current_turn = 0

    completed_now = False
    if state.status == GameStatus.in_progress:
        if len(playable_players) == 1:
            state.status = GameStatus.completed
            state.winner_id = playable_players[0]
            winner_name = get_username_by_id(playable_players[0], db)
            publish_system_log_event(game.link, f"{winner_name} won", state, db)
            completed_now = True
        elif len(playable_players) == 0:
            state.status = GameStatus.completed
            state.winner_id = None
            completed_now = True

    return playable_players, eliminated_players, completed_now


def set_next_playable_turn_after_current(game: Game, state: GameState, current_player_id: int, db: Session) -> tuple[List[int], List[int], bool]:
    """
    Advance turn ownership to the next player in original order who still has units.
    Also synchronizes state.players to only playable players and resolves game completion.
    """
    playable_players, eliminated_players, completed_now = reconcile_playable_players(game, state, db)
    if completed_now or not playable_players:
        return playable_players, eliminated_players, completed_now

    if state.current_turn is None:
        state.current_turn = 0
    else:
        state.current_turn = int(state.current_turn) + 1

    # Keep turn owner aligned with currently playable players after increment.
    if playable_players:
        _ = playable_players[state.current_turn % len(playable_players)]

    return playable_players, eliminated_players, completed_now


def advance_turn_if_player_has_no_actions(
    game: Game,
    state: GameState,
    current_player_id: int,
    db: Session,
    removed_ids: List[int] | None = None,
) -> tuple[List[int], bool, bool]:
    """
    If the current player has no units with can_move remaining, advance the turn.
    Returns (removed_ids, turn_advanced, game_completed).
    """
    remaining_units = (
        db.query(GameUnit)
        .filter(
            GameUnit.game_id == game.id,
            GameUnit.user_id == current_player_id,
            GameUnit.can_move == True,
        )
        .count()
    )
    if remaining_units > 0:
        return removed_ids or [], False, False

    removed_ids = list(removed_ids or [])

    units_to_sync = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
    for unit in units_to_sync:
        unit.starting_x = unit.current_x
        unit.starting_y = unit.current_y

    end_turn_modified_unit_ids = set(apply_end_of_turn_status_damage(current_player_id, game.id, db))
    should_apply_round_weather = ((state.current_turn + 1) % len(state.players)) == 0
    if should_apply_round_weather:
        end_turn_modified_unit_ids.update(apply_end_of_round_weather_damage(game.id, db))
        end_turn_modified_unit_ids.update(
            apply_end_of_round_entry_hazard_effects(game.id, state.current_turn, db)
        )
        decrement_and_expire_hazards(game.id, db)

    end_turn_removed_ids = remove_fainted_units_from_play(game.id, db)
    if end_turn_removed_ids:
        removed_ids = list(set(removed_ids + end_turn_removed_ids))

    remaining_units_after_end_turn_damage = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
    remaining_players_after_end_turn_damage = {unit.user_id for unit in remaining_units_after_end_turn_damage}
    if len(remaining_players_after_end_turn_damage) == 1:
        state.status = GameStatus.completed
        state.winner_id = next(iter(remaining_players_after_end_turn_damage))
        winner_name = get_username_by_id(state.winner_id, db)
        publish_system_log_event(game.link, f"{winner_name} won", state, db)
        db.commit()
        for unit_id in removed_ids:
            redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return removed_ids, False, True

    current_player_units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game.id, GameUnit.user_id == current_player_id)
        .all()
    )
    for unit in current_player_units:
        unit.can_move = True

    playable_players, _, completed_now = set_next_playable_turn_after_current(
        game, state, current_player_id, db
    )
    if completed_now:
        db.commit()
        for unit_id in removed_ids:
            redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return removed_ids, False, True

    if not playable_players:
        raise HTTPException(status_code=400, detail="Invalid game state")

    new_current_player_id = playable_players[state.current_turn % len(playable_players)]
    modified_unit_ids = set(end_turn_modified_unit_ids)
    modified_unit_ids.update(decrement_and_expire_stat_boosts(new_current_player_id, game.id, db))
    modified_unit_ids.update(
        decrement_and_expire_status_effects(new_current_player_id, game.id, db, game, state)
    )
    removed_ids.extend(remove_fainted_units_from_play(game.id, db))

    for unit_id in modified_unit_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_stats_updated:{unit_id}")

    if game.max_turns and state.current_turn >= game.max_turns * len(state.players):
        state.status = GameStatus.completed
        db.commit()
        for unit_id in removed_ids:
            redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return removed_ids, False, True

    now = datetime.now(timezone.utc)
    state.turn_deadline = now + timedelta(seconds=game.turn_seconds)
    compute_turn_locks(game, state, db)
    publish_turn_start_logs(game, state, db)
    db.commit()
    for unit_id in removed_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
    redis_client.publish(f"game_updates:{game.link}", "turn_advanced")
    redis_client.publish(f"game_updates:{game.link}", "turn_started")
    return removed_ids, True, False


def get_draw_player_ids(game: Game, state: GameState, db: Session) -> List[int]:
    counts = get_remaining_unit_counts(game.id, db)
    if not counts:
        return list(state.players or [])
    max_count = max(counts.values())
    return [pid for pid, count in counts.items() if count == max_count]


def _build_2d_matrix(height: int, width: int, fill_value):
    return [[fill_value for _ in range(width)] for _ in range(height)]


def _build_hazard_2d_matrix(height: int, width: int):
    return [[[] for _ in range(width)] for _ in range(height)]


def _normalize_item_id_tiles_from_map(map_obj: Map):
    height = map_obj.height
    width = map_obj.width
    default = _build_2d_matrix(height, width, None)

    tile_data = map_obj.tile_data
    if not isinstance(tile_data, dict):
        return default

    raw = tile_data.get("item_id_tiles")
    if not isinstance(raw, list):
        return default

    result = _build_2d_matrix(height, width, None)
    for y in range(min(height, len(raw))):
        row = raw[y]
        if not isinstance(row, list):
            continue
        for x in range(min(width, len(row))):
            value = row[x]
            if isinstance(value, int) and value >= 0:
                result[y][x] = value
    return result


RANDOM_TM_ITEM_ID = 0


def _resolve_random_tm_tiles(map_state: GameMapState, db: Session) -> bool:
    tiles = map_state.item_id_tiles
    if not tiles:
        return False

    tm_ids = [
        item.id
        for item in db.query(Item).filter(Item.category == "tm").all()
    ]
    if not tm_ids:
        return False

    changed = False
    new_tiles = []
    for row in tiles:
        new_row = []
        for value in row:
            if value == RANDOM_TM_ITEM_ID:
                new_row.append(random.choice(tm_ids))
                changed = True
            else:
                new_row.append(value)
        new_tiles.append(new_row)

    if changed:
        map_state.item_id_tiles = new_tiles
    return changed


def _resolve_random_tm_tiles_for_game(game: Game, db: Session) -> None:
    map_state = db.query(GameMapState).filter_by(game_id=game.id).first()
    if map_state:
        _resolve_random_tm_tiles(map_state, db)


def _create_default_game_map_state(game: Game, map_obj: Map) -> GameMapState:
    return GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=_build_2d_matrix(map_obj.height, map_obj.width, 0),
        hazard_tiles=_build_hazard_2d_matrix(map_obj.height, map_obj.width),
        room_effect_tiles=_build_2d_matrix(map_obj.height, map_obj.width, 0),
        terrain_effect_tiles=_build_2d_matrix(map_obj.height, map_obj.width, 0),
        field_effect_tiles=_build_2d_matrix(map_obj.height, map_obj.width, 0),
        item_id_tiles=_normalize_item_id_tiles_from_map(map_obj),
    )


def _get_or_create_game_map_state(game: Game, db: Session) -> GameMapState:
    map_state = (
        db.query(GameMapState)
        .options(joinedload(GameMapState.map))
        .filter(GameMapState.game_id == game.id)
        .first()
    )
    if map_state and map_state.map:
        return map_state

    # Fallback for legacy rows created before GameMapState existed.
    map_obj = db.query(Map).filter_by(id=game.map_id).first()
    if not map_obj:
        raise HTTPException(status_code=500, detail="Map missing for game")

    if map_state is None:
        map_state = _create_default_game_map_state(game, map_obj)
        db.add(map_state)
    else:
        map_state.map_id = map_obj.id
        db.add(map_state)

    db.commit()
    return (
        db.query(GameMapState)
        .options(joinedload(GameMapState.map))
        .filter(GameMapState.game_id == game.id)
        .first()
    )


def _get_map_via_game_state(game: Game, db: Session) -> Map:
    return _get_or_create_game_map_state(game, db).map

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

    map_obj = _get_map_via_game_state(game, db)
    map_state_obj = _get_or_create_game_map_state(game, db)

    draw_player_ids = None
    if game_state.status == GameStatus.completed and game_state.winner_id is None:
        draw_player_ids = get_draw_player_ids(game, game_state, db)

    return GameResponse(
        id=game.id,
        status=game_state.status,
        is_private=game.is_private,
        game_name=game.game_name,
        map_name=game.map_name,
        map=MapDetail.model_validate(map_obj),
        map_state=GameMapStateSchema.model_validate(map_state_obj),
        max_players=game.max_players,
        host_id=game.host_id,
        players=players,
        player_order=game_state.players,
        winner_id=game_state.winner_id,
        draw_player_ids=draw_player_ids,
        gamemode=game.gamemode,
        current_turn=game_state.current_turn,
        starting_cash=game.starting_cash,
        cash_per_turn=game.cash_per_turn,
        max_turns=game.max_turns,
        unit_limit=game.unit_limit,
        turn_seconds=game.turn_seconds,
        start_with_tms=game.start_with_tms,
        turn_deadline=game_state.turn_deadline,
        replay_log=game_state.replay_log,
        link=game.link,
        timestamp=game.timestamp
    )

def advance_if_expired(game: Game, state: GameState, db: Session) -> bool:
    """Advance to the next player if the turn timer elapsed. Returns True if advanced."""
    if state.status != GameStatus.in_progress or not state.turn_deadline:
        return False

    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return True
    if not playable_players:
        return False

    now = datetime.now(timezone.utc)
    warning_published = publish_turn_remaining_warning_if_needed(game, state, db, now)
    if now < state.turn_deadline:
        if warning_published:
            db.commit()
        return False

    # Sync all units' starting positions to current positions before advancing turn
    units_to_sync = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
    for unit in units_to_sync:
        unit.starting_x = unit.current_x
        unit.starting_y = unit.current_y

    # Resolve end-of-turn status damage for the current player before advancing.
    current_player_id = state.players[state.current_turn % len(state.players)]
    end_turn_modified_unit_ids = set(apply_end_of_turn_status_damage(current_player_id, game.id, db))
    should_apply_round_weather = ((state.current_turn + 1) % len(state.players)) == 0
    if should_apply_round_weather:
        end_turn_modified_unit_ids.update(apply_end_of_round_weather_damage(game.id, db))
        end_turn_modified_unit_ids.update(apply_end_of_round_entry_hazard_effects(game.id, state.current_turn, db))
        decrement_and_expire_hazards(game.id, db)

    removed_ids = remove_fainted_units_from_play(game.id, db)

    # Reset can_move for the current player's units before advancing turn
    current_player_units = db.query(GameUnit).filter(
        GameUnit.game_id == game.id,
        GameUnit.user_id == current_player_id
    ).all()
    for unit in current_player_units:
        unit.can_move = True

    playable_players, _, completed_now = set_next_playable_turn_after_current(game, state, current_player_id, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return True
    if not playable_players:
        return False

    # Decrement and expire stat boosts/statuses for the new current player's units.
    new_current_player_id = playable_players[state.current_turn % len(playable_players)]
    modified_unit_ids = set(end_turn_modified_unit_ids)
    modified_unit_ids.update(decrement_and_expire_stat_boosts(new_current_player_id, game.id, db))
    modified_unit_ids.update(
        decrement_and_expire_status_effects(new_current_player_id, game.id, db, game, state)
    )
    removed_ids.extend(remove_fainted_units_from_play(game.id, db))
    
    # Broadcast stat updates for units that had boosts expire
    for unit_id in modified_unit_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_stats_updated:{unit_id}")

    for unit_id in removed_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")

    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return True
    
    # Check if game should be completed (max_turns represents full rounds, not individual player turns)
    if game.max_turns and state.current_turn >= game.max_turns * len(state.players):
        draw_player_ids = get_draw_player_ids(game, state, db)
        state.status = GameStatus.completed
        if len(draw_player_ids) == 1:
            state.winner_id = draw_player_ids[0]
        else:
            state.winner_id = None
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return True
    
    state.turn_deadline = now + timedelta(seconds=game.turn_seconds)

    compute_turn_locks(game, state, db)
    publish_turn_start_logs(game, state, db)
    db.commit()
    redis_client.publish(f"game_updates:{game.link}", "turn_advanced")
    redis_client.publish(f"game_updates:{game.link}", "turn_started")
    return True

def movement_range_backend(start, rng, movement_costs, width, height, blocked_tiles: set[tuple[int, int]] | None = None):
    sx, sy = start
    blocked_tiles = blocked_tiles or set()
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
                if (nx, ny) in blocked_tiles:
                    continue
                step_cost = movement_costs[ny][nx]
                if step_cost >= IMPOSSIBLE_MOVEMENT_COST:
                    continue
                nc = c + step_cost
                if nc <= rng and (nx, ny) not in seen:
                    q.append((nx, ny, nc))
    return out

def compute_turn_locks(game: Game, state: GameState, db: Session):
    """Cache {unit_id: {origin:[x,y], tiles:[[...],...]}} for the player whose turn it is."""
    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now or state.current_turn is None or not playable_players:
        return

    # Derive the current player from the turn counter
    current_player_id = playable_players[state.current_turn % len(playable_players)]

    map_obj = db.query(Map).filter_by(id=game.map_id).first()
    costs = map_obj.tile_data["movement_cost"]
    special_tiles = map_obj.tile_data.get("special_tiles")
    width, height = map_obj.width, map_obj.height
    units = (
        db.query(GameUnit)
        .join(Unit, Unit.id == GameUnit.unit_id)
        .filter(GameUnit.game_id == game.id, GameUnit.user_id == current_player_id)
        .all()
    )

    enemy_blocked_tiles = {
        (unit.current_x, unit.current_y)
        for unit in db.query(GameUnit)
        .filter(
            GameUnit.game_id == game.id,
            GameUnit.user_id != current_player_id,
            GameUnit.current_hp > 0,
        )
        .all()
    }

    key = f"turnlock:{game.link}:{current_player_id}"
    redis_client.delete(key)

    # Store as a hash: field=unit_id, value=json
    for gu in units:
        clear_movement_locked(game.link, gu.id)
        if (gu.current_hp or 0) <= 0:
            continue
        current_stats = gu.current_stats or {}
        rng = int(current_stats.get("range", 0) or 0)
        unit_types = get_unit_types(gu, db)
        ability_names = get_unit_ability_names(gu, db)
        blocked_tiles = (
            set()
            if unit_can_pass_through_units(unit_types)
            else enemy_blocked_tiles
        )
        effective_costs = build_movement_cost_grid(
            costs,
            special_tiles,
            unit_types,
            ability_names,
        )
        tiles = movement_range_with_terrain(
            (gu.starting_x, gu.starting_y),
            rng,
            effective_costs,
            special_tiles,
            width,
            height,
            unit_types,
            ability_names,
            blocked_tiles,
        )
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
        .filter(
            GameState.status.in_([GameStatus.in_progress, GameStatus.preparation]),
            Game.is_private == False,
        )
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
        start_with_tms=data.start_with_tms,
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

    game_map_state = GameMapState(
        game_id=new_game.id,
        map_id=selected_map.id,
        weather_tiles=_build_2d_matrix(selected_map.height, selected_map.width, 0),
        hazard_tiles=_build_hazard_2d_matrix(selected_map.height, selected_map.width),
        room_effect_tiles=_build_2d_matrix(selected_map.height, selected_map.width, 0),
        terrain_effect_tiles=_build_2d_matrix(selected_map.height, selected_map.width, 0),
        field_effect_tiles=_build_2d_matrix(selected_map.height, selected_map.width, 0),
        item_id_tiles=_normalize_item_id_tiles_from_map(selected_map),
    )
    db.add(game_map_state)

    publish_system_log_event(new_game.link, f"{user.username} created the lobby", game_state, db)

    db.commit()
    db.refresh(new_game)

    return GameResponse(
        id=new_game.id,
        status=game_state.status,
        is_private=new_game.is_private,
        game_name=new_game.game_name,
        map_name=new_game.map_name,
        map=MapDetail.model_validate(selected_map),
        map_state=GameMapStateSchema.model_validate(game_map_state),
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
        start_with_tms=new_game.start_with_tms,
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

    publish_system_log_event(game.link, f"{user.username} joined the game", game_state, db)

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
        map=MapDetail.model_validate(_get_map_via_game_state(game, db)),
        map_state=GameMapStateSchema.model_validate(_get_or_create_game_map_state(game, db)),
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
        start_with_tms=game.start_with_tms,
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
            _resolve_random_tm_tiles_for_game(game, db)
            publish_system_log_event(
                game.link,
                "The game has begun! All players may now select their units",
                game_state,
                db,
            )
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_preparation")
            return {"detail": "Game moved to preparation phase"}
        elif game_state.status == GameStatus.preparation:
            game_state.status = GameStatus.in_progress
            _resolve_random_tm_tiles_for_game(game, db)

            if game_state.players:
                game_state.current_turn = 0
                game_state.turn_deadline = datetime.now(timezone.utc) + timedelta(seconds=game.turn_seconds)

            compute_turn_locks(game, game_state, db)
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_started")        
            redis_client.publish(f"game_updates:{game.link}", "turn_started")
            publish_system_log_event(game.link, f"{user.username} started the game", game_state, db)
            publish_turn_start_logs(game, game_state, db)
            db.commit()
            return {"detail": "Game started"}
        else:
            raise HTTPException(status_code=400, detail="Game already in progress or completed")
    else:
        game_state.status = GameStatus.in_progress
        _resolve_random_tm_tiles_for_game(game, db)

        if game_state.players:
                game_state.current_turn = 0
                game_state.turn_deadline = datetime.now(timezone.utc) + timedelta(seconds=game.turn_seconds)

        compute_turn_locks(game, game_state, db)
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_started")
        redis_client.publish(f"game_updates:{game.link}", "turn_started")
        publish_system_log_event(game.link, f"{user.username} started the game", game_state, db)
        publish_turn_start_logs(game, game_state, db)
        db.commit()
        return {"detail": "Game started"}


@router.post("/{link}/chat")
def send_chat_message(
    link: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter(GameState.game_id == game.id).first()
    if not state or user.id not in (state.players or []):
        raise HTTPException(status_code=403, detail="You are not in this game")

    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(message) > 300:
        raise HTTPException(status_code=400, detail="Message too long")

    ensure_user_can_chat(user, db)
    censored_message, _infraction = apply_chat_moderation(
        db,
        user_id=user.id,
        game_id=game.id,
        message=message,
    )

    publish_chat_message_event(game.link, user.id, user.username, censored_message, state, db)
    db.commit()
    return {"ok": True}

@router.get("/{link}", response_model=GameResponse)
def get_game_by_link(
    link: str,
    db: Session = Depends(get_db)
):
    game = (
        db.query(Game)
        .options(joinedload(Game.map_state).joinedload(GameMapState.map), joinedload(Game.player_states))
        .filter(Game.link == link)
        .first()
    )
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    removed_ids = remove_fainted_units_from_play(game.id, db)
    if removed_ids:
        db.commit()
        for unit_id in removed_ids:
            redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")

    game_state = db.query(GameState).filter_by(game_id=game.id).first()
    _, _, completed_now = reconcile_playable_players(game, game_state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")

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
        map=MapDetail.model_validate(_get_map_via_game_state(game, db)),
        map_state=GameMapStateSchema.model_validate(_get_or_create_game_map_state(game, db)),
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
        start_with_tms=game.start_with_tms,
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

    if player_state.is_ready:
        publish_system_log_event(game.link, f"{user.username} is ready to start", game_state, db)
    else:
        publish_system_log_event(game.link, f"{user.username} needs more time", game_state, db)

    db.commit()

    redis_client.publish(f"game_updates:{game.link}", "player_ready")
    return {"ready": player_state.is_ready}

@router.get("/{link}/units", response_model=List[GameUnitSchema])
def get_game_units(
    link: str,
    db: Session = Depends(get_db)
):
    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    removed_ids = remove_fainted_units_from_play(game.id, db)
    if removed_ids:
        db.commit()
        for unit_id in removed_ids:
            redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if state and state.status == GameStatus.in_progress:
        _, _, completed_now = reconcile_playable_players(game, state, db)
        if completed_now:
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_completed")

    # Expire session objects to ensure fresh data from database
    db.expire_all()
    units = (
        db.query(GameUnit)
        .options(joinedload(GameUnit.unit))
        .filter(GameUnit.game_id == game.id)
        .all()
    )
    
    # Ensure move_pp is properly populated for each unit
    for unit in units:
        if unit.move_pp is None:
            unit.move_pp = []
        elif not isinstance(unit.move_pp, list):
            unit.move_pp = list(unit.move_pp) if unit.move_pp else []
        unit.status_effects = normalize_status_effects(unit.status_effects)
        unit.states = normalize_states(unit.states)
        
        # Ensure current_stats is properly populated - recalculate if missing keys
        if not isinstance(unit.current_stats, dict) or not unit.current_stats:
            unit.current_stats = compute_effective_stats(unit, db)
        else:
            # Check if all expected stat keys are present
            unit_info = db.query(Unit).filter_by(id=unit.unit_id).first()
            if unit_info and isinstance(unit_info.base_stats, dict):
                expected_keys = set(unit_info.base_stats.keys())
                actual_keys = set(unit.current_stats.keys())
                # If any expected stat is missing, recalculate
                if not expected_keys.issubset(actual_keys):
                    unit.current_stats = compute_effective_stats(unit, db)

        if unit.unit:
            sync_tm_move_pp(unit, unit.unit, db)
        attach_game_unit_loadout_fields(unit, db)
    
    return units

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

    map_obj = db.query(Map).filter_by(id=game.map_id).first()
    special_tiles = map_obj.tile_data.get("special_tiles") if map_obj else None
    unit_types = {str(t).lower() for t in (unit_info.types or [])}
    if map_obj and not unit_can_occupy_tile(special_tiles, unit_data.x, unit_data.y, unit_types):
        raise HTTPException(status_code=400, detail="This unit cannot be placed on this tile")

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

    # Initialize move_pp with full PP values from the unit's equipped moves
    equipped_move_ids = get_default_equipped_move_ids(unit_info, level)
    move_pp = []
    for move_id in equipped_move_ids:
        move = db.query(Move).filter_by(id=move_id).first()
        if move and move.pp is not None:
            move_pp.append(move.pp)
        else:
            move_pp.append(0)
    
    # Step 1: Create and persist new GameUnit
    initial_flags: dict = {}
    if equipped_move_ids:
        initial_flags["move_ids"] = equipped_move_ids
    if unit_info.ability_ids:
        initial_flags["ability_id"] = int(unit_info.ability_ids[0])

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
        current_stats=current_stats,  # Initial stats without boosts
        stat_boosts=normalize_stat_boosts(unit_data.stat_boosts),
        status_effects=normalize_status_effects(unit_data.status_effects),
        states=normalize_states(unit_data.states),
        is_fainted=unit_data.is_fainted,
        move_pp=move_pp,
        flags=initial_flags,
    )
    db.add(new_unit)
    db.flush()
    
    # Recalculate current_stats to apply any initial stat boosts
    new_unit.current_stats = compute_effective_stats(new_unit, db)
    # Ensure current_stats has all expected keys
    unit_info_for_stats = db.query(Unit).filter_by(id=new_unit.unit_id).first()
    if unit_info_for_stats and isinstance(unit_info_for_stats.base_stats, dict):
        for stat_name in unit_info_for_stats.base_stats.keys():
            if stat_name.lower() != "range" and stat_name not in new_unit.current_stats:
                # Fallback calculation if stat is missing
                base_value = unit_info_for_stats.base_stats[stat_name]
                level = new_unit.level or 50
                if stat_name.lower() == "hp":
                    new_unit.current_stats[stat_name] = int((2 * base_value * level) / 100) + level + 10
                else:
                    base_stat = int((2 * base_value * level) / 100 + 5)
                    multiplier = get_stat_multiplier(new_unit.stat_boosts, stat_name)
                    new_unit.current_stats[stat_name] = int(base_stat * multiplier)
    
    db.add(new_unit)

    # Step 2: Update player state
    player_state.cash_remaining -= unit_info.cost
    player_state.game_units.append(new_unit.id)

    # Step 3: Ensure SQLAlchemy registers state as dirty
    db.add(player_state)

    db.commit()
    db.refresh(new_unit)

    attach_game_unit_loadout_fields(new_unit, db)
    return new_unit

@router.post("/{link}/units/{unit_id}/item", response_model=GameUnitChangeItemResponse)
def change_unit_item(
    link: str,
    unit_id: int,
    payload: GameUnitChangeItemRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = db.query(Game).filter_by(link=link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.preparation:
        raise HTTPException(status_code=400, detail="Items can only be changed during the preparation phase")

    unit = (
        db.query(GameUnit)
        .options(joinedload(GameUnit.unit))
        .filter_by(id=unit_id, game_id=game.id, user_id=user.id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=user.id).first()
    if not player_state:
        raise HTTPException(status_code=404, detail="Player state not found")

    new_item = db.query(Item).filter_by(id=payload.item_id).first()
    if not new_item:
        raise HTTPException(status_code=404, detail="Item not found")

    if not preparation_item_allowed(new_item, game):
        raise HTTPException(status_code=400, detail="TM items are not enabled for this game")

    old_slug = get_unit_held_item(unit)
    if old_slug == new_item.slug:
        attach_game_unit_loadout_fields(unit, db)
        return GameUnitChangeItemResponse(unit=unit, cash_remaining=player_state.cash_remaining)

    old_item = resolve_item_record(old_slug, db)
    old_cost = old_item.cost if old_item else 0
    net_cost = new_item.cost - old_cost
    if player_state.cash_remaining < net_cost:
        raise HTTPException(status_code=400, detail="Not enough cash")

    player_state.cash_remaining -= net_cost
    set_unit_held_item(unit, new_item.slug, db)
    sync_tm_move_pp(unit, unit.unit, db)
    db.add(player_state)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    attach_game_unit_loadout_fields(unit, db)
    return GameUnitChangeItemResponse(unit=unit, cash_remaining=player_state.cash_remaining)

@router.delete("/{link}/units/{unit_id}/item", response_model=GameUnitChangeItemResponse)
def remove_unit_item(
    link: str,
    unit_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = db.query(Game).filter_by(link=link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.preparation:
        raise HTTPException(status_code=400, detail="Items can only be changed during the preparation phase")

    unit = (
        db.query(GameUnit)
        .options(joinedload(GameUnit.unit))
        .filter_by(id=unit_id, game_id=game.id, user_id=user.id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=user.id).first()
    if not player_state:
        raise HTTPException(status_code=404, detail="Player state not found")

    old_slug = get_unit_held_item(unit)
    if not old_slug:
        attach_game_unit_loadout_fields(unit, db)
        return GameUnitChangeItemResponse(unit=unit, cash_remaining=player_state.cash_remaining)

    old_item = resolve_item_record(old_slug, db)
    if old_item:
        player_state.cash_remaining += old_item.cost

    set_unit_held_item(unit, None, db)
    sync_tm_move_pp(unit, unit.unit, db)
    db.add(player_state)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    attach_game_unit_loadout_fields(unit, db)
    return GameUnitChangeItemResponse(unit=unit, cash_remaining=player_state.cash_remaining)

@router.post("/{link}/units/{unit_id}/ability", response_model=GameUnitChangeAbilityResponse)
def change_unit_ability(
    link: str,
    unit_id: int,
    payload: GameUnitChangeAbilityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    game = db.query(Game).filter_by(link=link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.preparation:
        raise HTTPException(status_code=400, detail="Abilities can only be changed during the preparation phase")

    unit = (
        db.query(GameUnit)
        .options(joinedload(GameUnit.unit))
        .filter_by(id=unit_id, game_id=game.id, user_id=user.id)
        .first()
    )
    if not unit or not unit.unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=user.id).first()
    if not player_state:
        raise HTTPException(status_code=404, detail="Player state not found")

    unit_info = unit.unit
    new_ability_id = int(payload.ability_id)
    if not unit_can_learn_ability(unit_info, new_ability_id):
        raise HTTPException(status_code=400, detail="This unit cannot learn that ability")

    current_ability_id = get_unit_ability_id(unit)
    if current_ability_id == new_ability_id:
        attach_game_unit_loadout_fields(unit, db)
        return GameUnitChangeAbilityResponse(unit=unit, cash_remaining=player_state.cash_remaining)

    net_cost = ability_change_net_cost(unit_info, current_ability_id, new_ability_id)
    if player_state.cash_remaining < net_cost:
        raise HTTPException(status_code=400, detail="Not enough cash")

    player_state.cash_remaining -= net_cost
    set_unit_ability_id(unit, new_ability_id, db)
    db.add(player_state)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    attach_game_unit_loadout_fields(unit, db)
    return GameUnitChangeAbilityResponse(unit=unit, cash_remaining=player_state.cash_remaining)

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
    equipped_item = resolve_item_record(get_unit_held_item(unit), db)
    if equipped_item:
        player_state.cash_remaining += equipped_item.cost
    if is_hidden_ability_for_unit(unit_info, get_unit_ability_id(unit)):
        player_state.cash_remaining += HIDDEN_ABILITY_COST
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
    if not state:
        return {}

    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return {}

    # Return the locks for the player whose turn it is (i.e., the “frozen” sets)
    if not playable_players or state.current_turn is None:
        return {}
    current_player_id = playable_players[state.current_turn % len(playable_players)]
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
    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return {"detail": "Game completed"}

    if not playable_players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")

    current_player_id = playable_players[state.current_turn % len(playable_players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    units_to_sync = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
    for unit in units_to_sync:
        unit.starting_x = unit.current_x
        unit.starting_y = unit.current_y

    # Resolve end-of-turn status damage for the current player before advancing.
    end_turn_modified_unit_ids = set(apply_end_of_turn_status_damage(current_player_id, game.id, db))
    should_apply_round_weather = ((state.current_turn + 1) % len(state.players)) == 0
    if should_apply_round_weather:
        end_turn_modified_unit_ids.update(apply_end_of_round_weather_damage(game.id, db))
        end_turn_modified_unit_ids.update(apply_end_of_round_entry_hazard_effects(game.id, state.current_turn, db))
        decrement_and_expire_hazards(game.id, db)

    removed_ids = remove_fainted_units_from_play(game.id, db)

    # Reset can_move for the current player's units before advancing turn
    current_player_units = db.query(GameUnit).filter(
        GameUnit.game_id == game.id,
        GameUnit.user_id == current_player_id
    ).all()
    for unit in current_player_units:
        unit.can_move = True

    playable_players, _, completed_now = set_next_playable_turn_after_current(game, state, current_player_id, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return {"detail": "Game completed"}
    if not playable_players:
        raise HTTPException(status_code=400, detail="Invalid game state")

    new_current_player_id = playable_players[state.current_turn % len(playable_players)]
    modified_unit_ids = set(end_turn_modified_unit_ids)
    modified_unit_ids.update(decrement_and_expire_stat_boosts(new_current_player_id, game.id, db))
    modified_unit_ids.update(
        decrement_and_expire_status_effects(new_current_player_id, game.id, db, game, state)
    )
    removed_ids.extend(remove_fainted_units_from_play(game.id, db))

    for unit_id in modified_unit_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_stats_updated:{unit_id}")

    for unit_id in removed_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")

    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return {"detail": "Game completed"}

    # Check if game should be completed (max_turns represents full rounds, not individual player turns)
    if game.max_turns and state.current_turn >= game.max_turns * len(state.players):
        draw_player_ids = get_draw_player_ids(game, state, db)
        state.status = GameStatus.completed
        if len(draw_player_ids) == 1:
            state.winner_id = draw_player_ids[0]
        else:
            state.winner_id = None
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        return {"detail": "Game completed"}

    now = datetime.now(timezone.utc)
    state.turn_deadline = now + timedelta(seconds=game.turn_seconds)

    compute_turn_locks(game, state, db)
    publish_turn_start_logs(game, state, db)
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

    raw_effect_tiles = payload.get("effect_tiles") or []
    effect_tiles: list[tuple[int, int]] = []
    if isinstance(raw_effect_tiles, list):
        for tile in raw_effect_tiles:
            if not isinstance(tile, list) or len(tile) < 2:
                continue
            try:
                tx = int(tile[0])
                ty = int(tile[1])
            except (TypeError, ValueError):
                continue
            effect_tiles.append((tx, ty))

    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.in_progress:
        raise HTTPException(status_code=400, detail="Game not in progress")
    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        raise HTTPException(status_code=400, detail="Game completed")

    if not playable_players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")

    current_player_id = playable_players[state.current_turn % len(playable_players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    gu = db.query(GameUnit).filter(GameUnit.id == unit_id, GameUnit.game_id == game.id).first()
    if not gu:
        raise HTTPException(status_code=404, detail="Unit not found")
    if gu.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only execute moves for your own unit")
    if not gu.can_move:
        raise HTTPException(status_code=400, detail="Unit is locked")

    # Enforce Encore: if unit is encored, it can only use the stored move id
    try:
        raw_state = gu.states if isinstance(gu.states, list) else []
        if isinstance(raw_state, list) and len(raw_state) >= 3 and str(raw_state[0]).lower() == "encore" and int(raw_state[1]) > 0:
            try:
                required_move_id = int(raw_state[2])
            except Exception:
                required_move_id = None
            if required_move_id and required_move_id != move_id:
                mv = db.query(Move).filter(Move.id == required_move_id).first()
                mv_name = mv.name if mv else "the encored move"
                raise HTTPException(status_code=400, detail=f"Encore prevents that move; must use {mv_name}")
    except HTTPException:
        raise
    except Exception:
        pass

    # Load move early so we can enforce torment (requires move.name)
    move = db.query(Move).filter(Move.id == move_id).first()
    if not move:
        raise HTTPException(status_code=404, detail="Move not found")

    # Enforce Taunt and Torment: prevent using status moves while taunted,
    # and prevent using the same move twice in a row while tormented.
    try:
        gu_state_tmp = normalize_states(gu.states)
        if gu_state_tmp and gu_state_tmp[0] == "taunt" and int(gu_state_tmp[1]) > 0:
            if str((move.category or "")).lower() == "status":
                raise HTTPException(status_code=400, detail="Taunted and cannot use status moves")

        if gu_state_tmp and gu_state_tmp[0] == "torment" and int(gu_state_tmp[1]) > 0:
            # Find the last move used by this unit from the replay_log
            last_move_name = None
            if state and isinstance(state.replay_log, list):
                prefix = f"{get_unit_display_name(gu, db)} used "
                for entry in reversed(state.replay_log or []):
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("event") != "system_log":
                        continue
                    msg = str(entry.get("message") or "")
                    if msg.startswith(prefix):
                        last_move_name = msg[len(prefix) :]
                        break

            if last_move_name and last_move_name == (move.name or ""):
                raise HTTPException(status_code=400, detail="Tormented and cannot use the same move twice in a row")
    except HTTPException:
        raise
    except Exception:
        pass

    publish_system_log_event(game.link, f"{get_unit_display_name(gu, db)} used {move.name}", state, db)

    map_obj = db.query(Map).filter_by(id=game.map_id).first()
    map_state = db.query(GameMapState).filter(GameMapState.game_id == game.id).first()
    terrain_tiles = map_state.terrain_effect_tiles if map_state and isinstance(map_state.terrain_effect_tiles, list) else None
    field_effect_tiles = map_state.field_effect_tiles if map_state and isinstance(map_state.field_effect_tiles, list) else None
    weather_tiles = map_state.weather_tiles if map_state and isinstance(map_state.weather_tiles, list) else None

    special_tiles = (
        map_obj.tile_data.get("special_tiles")
        if map_obj and isinstance(map_obj.tile_data, dict)
        else None
    )
    attacker_types = get_unit_types(gu, db)

    # Check and decrement PP
    unit_info = db.query(Unit).filter_by(id=gu.unit_id).first()
    if not unit_info:
        raise HTTPException(status_code=400, detail="Unit has no moves")
    equipped_move_ids = get_unit_equipped_move_ids(gu, unit_info)
    if not equipped_move_ids and not get_held_tm_move_id(gu, db):
        raise HTTPException(status_code=400, detail="Unit has no moves")

    if not unit_knows_move(unit_info, move_id, gu, db):
        raise HTTPException(status_code=400, detail="Unit does not know this move")

    move_index = resolve_move_pp_index(gu, unit_info, move_id, db)
    if move_index is None:
        raise HTTPException(status_code=400, detail="Unit does not know this move")

    sync_tm_move_pp(gu, unit_info, db)
    
    # Ensure move_pp array is long enough
    if len(gu.move_pp) <= move_index:
        raise HTTPException(status_code=400, detail="PP data corrupted")
    
    current_pp = gu.move_pp[move_index]
    if current_pp <= 0:
        raise HTTPException(status_code=400, detail="Move has no PP left")
    
    # Decrement PP - reassign the entire list to ensure SQLAlchemy detects the change
    new_pp_list = gu.move_pp.copy()
    new_pp_list[move_index] = max(0, current_pp - 1)
    gu.move_pp = new_pp_list
    db.add(gu)

    targets: List[GameUnit] = []
    if target_ids:
        targets = (
            db.query(GameUnit)
            .filter(GameUnit.game_id == game.id, GameUnit.id.in_(target_ids))
            .all()
        )

    move_targeting = (move.targeting or "").lower()
    if effect_tiles and move_targeting == "ally":
        tile_set = set(effect_tiles)
        known_target_ids = {target.id for target in targets}
        try:
            ally_units = (
                db.query(GameUnit)
                .filter(GameUnit.game_id == game.id, GameUnit.user_id == gu.user_id)
                .all()
            )
        except Exception:
            ally_units = []
        for ally in ally_units:
            if ally.id in known_target_ids:
                continue
            if move_has_revive_effect(move):
                if not ally.is_fainted and int(ally.current_hp or 0) > 0:
                    continue
            elif (ally.current_hp or 0) <= 0:
                continue
            if (int(ally.current_x), int(ally.current_y)) in tile_set:
                targets.append(ally)
                known_target_ids.add(ally.id)

    if move_targeting == "all":
        tile_set = set(effect_tiles)
        if not tile_set and map_obj:
            tile_set = set(
                get_move_affected_tiles(
                    move,
                    gu,
                    int(getattr(map_obj, "width", 0) or 0),
                    int(getattr(map_obj, "height", 0) or 0),
                )
            )
        if tile_set:
            known_target_ids = {target.id for target in targets}
            all_units = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
            targets = []
            for unit in all_units:
                if (unit.current_hp or 0) <= 0:
                    continue
                if (int(unit.current_x), int(unit.current_y)) in tile_set:
                    targets.append(unit)
                    known_target_ids.add(unit.id)

    # Field-targeting moves affect map state and should ignore unit target resolution.
    is_field_targeting = (move.targeting or "").lower() == "field"
    if is_field_targeting:
        targets = []

    if move_has_effect_token(move, "target:fixed_damage:last_damage_received"):
        flags = get_unit_flags(gu)
        last_attacker_id = flags.get("last_damage_attacker_id")
        if last_attacker_id is not None:
            try:
                last_attacker = (
                    db.query(GameUnit)
                    .filter(GameUnit.game_id == game.id, GameUnit.id == int(last_attacker_id))
                    .first()
                )
            except (TypeError, ValueError):
                last_attacker = None
            if last_attacker is not None and int(last_attacker.current_hp or 0) > 0:
                targets = [last_attacker]

    move_failure = validate_move_execution(move, gu, targets, terrain_tiles, db)
    if move_failure:
        publish_system_log_event(game.link, move_failure, state, db)
        db.commit()
        return {
            "detail": "Move failed",
            "message": move_failure,
            "missed_target_ids": [],
            "damage_results": [],
            "removed_ids": [],
            "turn_advanced": False,
            "game_completed": False,
        }

    has_target_fixed_damage = move_has_target_fixed_damage_effect(move)

    # Build a mapping of player sides to any active screen states (reflect/light_screen)
    side_screen_states: dict[int, set[str]] = {}
    try:
        all_units = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
    except Exception:
        all_units = []
    for u in all_units:
        s = normalize_states(u.states)
        if s and isinstance(u.user_id, int):
            if int(s[1]) > 0:
                side_screen_states.setdefault(u.user_id, set()).add(s[0])

    landed_targets = targets
    missed_target_ids: List[int] = []
    if not is_field_targeting and targets and move.accuracy is not None and not has_target_fixed_damage:
        landed_targets = []
        for target in targets:
            try:
                t_state = normalize_states(target.states)
            except Exception:
                t_state = []

            tele_active = bool(t_state and t_state[0] == "telekinesis" and int(t_state[1]) > 0)

            # Telekinesis: Ground-type moves cannot hit the affected unit
            if tele_active and str((move.type or "")).lower() == "ground":
                missed_target_ids.append(target.id)
                continue

            # Telekinesis forces non-OHKO moves to hit
            if tele_active and not move_is_instant_ko(move):
                landed_targets.append(target)
                continue

            if move_lands_on_target(
                move,
                gu,
                target,
                special_tiles=special_tiles,
                weather_tiles=weather_tiles,
                attacker_types=attacker_types,
                target_types=get_unit_types(target, db),
                target_ability_names=get_unit_ability_names(target, db),
            ):
                landed_targets.append(target)
            else:
                missed_target_ids.append(target.id)

    if missed_target_ids:
        missed_targets = [target for target in targets if target.id in missed_target_ids]
        for missed_target in missed_targets:
            publish_system_log_event(
                game.link,
                f"{get_unit_display_name(missed_target, db)} dodged the attack",
                state,
                db,
            )

    targets_multiplier = 0.75 if len(landed_targets) >= 2 else 1
    hit_count = get_move_hit_count(move, landed_target_count=max(1, len(landed_targets)))
    scaling_hit_powers = get_scaling_hit_powers(move)
    separate_hit_accuracy = move_uses_separate_hit_accuracy(move)
    damage_results = []
    removed_ids: List[int] = []
    faint_logged_ids: set[int] = set()

    if landed_targets and has_target_fixed_damage:
        damage_results = apply_fixed_damage_move_effects(move, gu, landed_targets, db, hit_count=hit_count)
        for result in damage_results:
            dealt_damage = int(result.get("damage", 0) or 0)
            target_unit = next((t for t in landed_targets if t.id == int(result.get("id", -1))), None)
            if dealt_damage > 0 and target_unit is not None:
                publish_system_log_event(game.link, f"{get_unit_display_name(target_unit, db)} took {dealt_damage} damage", state, db)
            if int(result.get("current_hp", 0) or 0) <= 0:
                # Target fainted; check for Destiny Bond on the fainted unit
                removed_ids.append(result["id"])
                try:
                    # find the unit object for the fainted unit in the DB to read states
                    fainted_unit = db.query(GameUnit).filter(GameUnit.game_id == game.id, GameUnit.id == int(result.get("id", -1))).first()
                except Exception:
                    fainted_unit = target_unit
                if fainted_unit:
                    s = normalize_states(fainted_unit.states)
                    if s and s[0] == "destiny_bond" and int(s[1]) > 0:
                        # The fainted unit had Destiny Bond; knock out the attacker if still alive
                        if (gu.current_hp or 0) > 0:
                            gu.current_hp = 0
                            db.add(gu)
                            removed_ids.append(gu.id)
                            if game:
                                publish_system_log_event(game.link, f"{get_unit_display_name(gu, db)} was taken down by Destiny Bond!", state, db)
                if target_unit is not None and target_unit.id not in faint_logged_ids:
                    publish_system_log_event(game.link, f"{get_unit_display_name(target_unit, db)} fainted!", state, db)
                    faint_logged_ids.add(target_unit.id)
    elif landed_targets and move_deals_direct_damage(move):
        can_critical_hit = move_can_critical_hit(move)
        guaranteed_crit = move_has_effect_token(move, "guaranteed_crit")
        effective_move_type = resolve_move_type_for_execution(move, gu, terrain_tiles, db)
        category = (move.category or "").lower()
        is_special = category == "special"
        attack_stat = "sp_attack" if is_special else "attack"
        defense_stat = "sp_defense" if is_special else "defense"
        move_crit_stage_bonus = 1 if move_has_high_crit_ratio(move) else 0
        base_power = (move.power or 0) + resolve_power_add(move, gu)
        attacker_types = gu.unit.types or []
        stab = 1.5 if effective_move_type in attacker_types else 1
        attacker_weather_id = get_unit_weather_id(gu, weather_tiles)
        weather_move_multiplier = resolve_weather_move_multiplier_for_move(move, effective_move_type, attacker_weather_id)
        ignore_target_stats = move_ignores_target_stat_changes(move)
        ignore_fairy = move_ignores_fairy_immunity(move)

        for target in landed_targets:
            total_damage = 0
            critical_hit_landed = False
            target_is_special = is_special
            target_makes_contact = bool(move.makes_contact)
            if move_uses_best_offense(move):
                target_is_special, target_makes_contact = resolve_shell_side_arm_mode(
                    move,
                    gu,
                    target,
                    terrain_tiles=terrain_tiles,
                    weather_tiles=weather_tiles,
                    special_tiles=special_tiles,
                    db=db,
                    targets_multiplier=targets_multiplier,
                )
                attack_stat = "sp_attack" if target_is_special else "attack"
                defense_stat = "sp_defense" if target_is_special else "defense"

            power_multiplier = resolve_power_multiplier(
                move,
                gu,
                target,
                terrain_tiles,
                field_effect_tiles,
                db,
                weather_tiles=weather_tiles,
            )
            hit_powers = scaling_hit_powers or [base_power]
            hits_to_apply = len(hit_powers) if scaling_hit_powers else max(1, int(hit_count or 1))
            # Check if attacker has Laser Focus active; it should make the first hit a guaranteed critical
            try:
                attacker_state = normalize_states(gu.states)
            except Exception:
                attacker_state = []
            laser_focus_active = bool(attacker_state and attacker_state[0] == "laser_focus" and int(attacker_state[1]) > 0)
            first_hit = True
            for hit_index in range(hits_to_apply):
                if (target.current_hp or 0) <= 0:
                    break

                if separate_hit_accuracy and move.accuracy is not None:
                    if not move_lands_on_target(
                        move,
                        gu,
                        target,
                        special_tiles=special_tiles,
                        weather_tiles=weather_tiles,
                        attacker_types=attacker_types,
                        target_types=get_unit_types(target, db),
                        target_ability_names=get_unit_ability_names(target, db),
                    ):
                        break

                power = int((hit_powers[hit_index] if hit_index < len(hit_powers) else base_power) * power_multiplier)
                power = max(1, power)
                attack = (gu.current_stats or {}).get(attack_stat, 0) or 0
                if ignore_target_stats:
                    defense = get_unboosted_battle_stat(target, defense_stat, db)
                else:
                    defense = (target.current_stats or {}).get(defense_stat, 1) or 1
                for effect in move.effects or []:
                    parts = str(effect or "").strip().lower().split(":")
                    if len(parts) < 3 or parts[1] != "use_stat":
                        continue
                    stat = parts[2]
                    if parts[0] == "self":
                        attack = (gu.current_stats or {}).get(stat, attack) or attack
                    elif parts[0] == "target":
                        if stat in ("attack", "sp_attack"):
                            attack = (target.current_stats or {}).get(stat, attack) or attack
                        elif stat in ("defense", "sp_defense"):
                            defense = (target.current_stats or {}).get(stat, defense) or defense
                # Power Trick: swap attack/defense usage for attacker/defender when active
                try:
                    gu_state_tmp = normalize_states(gu.states)
                except Exception:
                    gu_state_tmp = []
                try:
                    target_state_tmp = normalize_states(target.states)
                except Exception:
                    target_state_tmp = []

                # If attacker has power_trick, use its defense stat as its attack value
                if gu_state_tmp and gu_state_tmp[0] == "power_trick" and int(gu_state_tmp[1]) > 0:
                    attack = (gu.current_stats or {}).get(defense_stat, attack)

                # If defender has power_trick, use its attack stat as its defense value
                if target_state_tmp and target_state_tmp[0] == "power_trick" and int(target_state_tmp[1]) > 0:
                    defense = (target.current_stats or {}).get(attack_stat, defense)
                target_weather_id = get_unit_weather_id(target, weather_tiles)
                weather_defense_multiplier = get_weather_defense_multiplier(target, defense_stat, target_weather_id, db)
                grass_defense_multiplier = get_tile_defense_multiplier(
                    special_tiles,
                    int(target.current_x),
                    int(target.current_y),
                    get_unit_types(target, db),
                    get_unit_ability_names(target, db),
                )
                effective_defense = defense * weather_defense_multiplier * grass_defense_multiplier
                safe_defense = effective_defense if effective_defense > 0 else 1
                random_factor = random.randint(85, 100) / 100
                # Apply Laser Focus: force first hit to be a critical and consume the state
                if laser_focus_active and first_hit:
                    critical = 1.5
                    critical_hit_landed = True
                    # consume laser_focus so subsequent hits are not critical
                    try:
                        gu.states = []
                        db.add(gu)
                    except Exception:
                        pass
                    laser_focus_active = False
                elif guaranteed_crit:
                    critical = 1.5
                    critical_hit_landed = True
                else:
                    critical = 1.5 if can_critical_hit and attempt_critical_hit(gu, move_crit_stage_bonus) else 1
                    if critical > 1:
                        critical_hit_landed = True
                # Pass the target unit so state effects like Foresight/Mind Reader
                # can bypass type immunities when appropriate.
                type_multiplier = get_type_multiplier(
                    effective_move_type,
                    (getattr(target.unit, "types", None) or [], target, db),
                    ignore_fairy_immunity=ignore_fairy,
                )
                # Tar Shot: doubles effectiveness of Fire-type moves against affected target
                try:
                    target_state_tmp = normalize_states(target.states)
                except Exception:
                    target_state_tmp = []
                if target_state_tmp and target_state_tmp[0] == "tar_shot" and int(target_state_tmp[1]) > 0 and str((move.type or "")).lower() == "fire":
                    type_multiplier = type_multiplier * 2
                base = (((2 * gu.level) / 5 + 2) * power * (attack / safe_defense)) / 50 + 2
                damage = int(base * targets_multiplier * random_factor * stab * critical * type_multiplier * weather_move_multiplier)
                if unit_has_glaive_rush(target):
                    damage *= 2
                # Apply side-wide screen reductions: Reflect halves physical damage,
                # Light Screen halves special damage for affected player's side.
                try:
                    states_on_side = side_screen_states.get(target.user_id, set())
                except Exception:
                    states_on_side = set()

                # Aurora Veil provides both effects; check it first
                if "aurora_veil" in states_on_side:
                    damage = max(0, int(damage // 2))
                else:
                    if "reflect" in states_on_side and not target_is_special:
                        damage = max(0, int(damage // 2))
                    if "light_screen" in states_on_side and target_is_special:
                        damage = max(0, int(damage // 2))

                target.current_hp = max(0, (target.current_hp or 0) - damage)
                total_damage += damage
                record_last_damage_received(target, gu, damage, db)
                first_hit = False

            if move_has_effect_token(move, "destroy_terrain:target") and map_state is not None:
                clear_terrain_at_position(map_state, int(target.current_x), int(target.current_y), db)

            db.add(target)
            if target.current_hp <= 0:
                # Check if the fainted target had Destiny Bond active
                s = normalize_states(target.states)
                if s and s[0] == "destiny_bond" and int(s[1]) > 0:
                    # Knock out the attacker (gu) if still alive
                    if (gu.current_hp or 0) > 0:
                        gu.current_hp = 0
                        db.add(gu)
                        removed_ids.append(gu.id)
                        if game:
                            publish_system_log_event(game.link, f"{get_unit_display_name(gu, db)} was taken down by Destiny Bond!", state, db)
                removed_ids.append(target.id)
            damage_results.append({"id": target.id, "damage": total_damage, "current_hp": target.current_hp})
            if total_damage > 0:
                damage_suffix = " (Critical Hit!)" if critical_hit_landed else ""
                publish_system_log_event(
                    game.link,
                    f"{get_unit_display_name(target, db)} took {total_damage} damage{damage_suffix}",
                    state,
                    db,
                )
                if target.current_hp <= 0 and target.id not in faint_logged_ids:
                    publish_system_log_event(game.link, f"{get_unit_display_name(target, db)} fainted!", state, db)
                    faint_logged_ids.add(target.id)

    # Process move effects (stat changes, status conditions, etc.)
    # Use targets list for target effects, even if empty
    process_move_effects(
        move,
        gu,
        landed_targets,
        state.current_turn,
        db,
        weather_tiles,
        terrain_tiles,
        field_effect_tiles,
        affected_tiles_override=effect_tiles,
        game=game,
        game_state=state,
    )

    # Capture any KOs caused by non-damage effects (e.g., instant_ko).
    post_effect_units = [gu] + targets
    for unit in post_effect_units:
        if int(unit.current_hp or 0) <= 0:
            removed_ids.append(unit.id)
    removed_ids = list(set(removed_ids))

    recoil_fainted_ids = apply_damage_based_move_effects(
        move,
        gu,
        landed_targets,
        damage_results,
        db,
        game=game,
        game_state=state,
        faint_logged_ids=faint_logged_ids,
    )
    if recoil_fainted_ids:
        removed_ids.extend(recoil_fainted_ids)
        removed_ids = list(set(removed_ids))
    
    # Broadcast stat updates for units that may have been affected
    # This includes the attacker (self-buffs) and all targets (debuffs/buffs)
    affected_unit_ids = [gu.id] + [t.id for t in targets]
    for unit_id in affected_unit_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_stats_updated:{unit_id}")

    if removed_ids:
        removed_units = (
            db.query(GameUnit)
            .filter(GameUnit.game_id == game.id, GameUnit.id.in_(removed_ids))
            .all()
        )

        removed_ids = [unit.id for unit in removed_units]
        for unit in removed_units:
            if unit.is_fainted:
                continue
            if int(unit.current_hp or 0) > 0:
                continue
            if unit.id not in faint_logged_ids:
                publish_system_log_event(game.link, f"{get_unit_display_name(unit, db)} fainted!", state, db)

            player_state = db.query(GamePlayer).filter_by(game_id=game.id, player_id=unit.user_id).first()
            if player_state and unit.id in player_state.game_units:
                player_state.game_units.remove(unit.id)
                db.add(player_state)

            faint_unit_in_place(unit, db)

        active_counts = get_remaining_unit_counts(game.id, db)
        affected_users = {unit.user_id for unit in removed_units}
        for user_id in affected_users:
            if active_counts.get(user_id, 0) == 0:
                username = get_username_by_id(user_id, db)
                publish_system_log_event(
                    game.link,
                    f"{username} has no more units and is unable to battle!",
                    state,
                    db,
                )

    if removed_ids:
        db.flush()
        remaining_players = set(get_remaining_unit_counts(game.id, db).keys())
        if len(remaining_players) == 1:
            state.status = GameStatus.completed
            state.winner_id = next(iter(remaining_players))
            winner_name = get_username_by_id(state.winner_id, db)
            publish_system_log_event(game.link, f"{winner_name} won", state, db)
            gu.can_move = False
            db.commit()
            for unit_id in removed_ids:
                redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
            redis_client.publish(f"game_updates:{game.link}", "game_completed")
            redis_client.publish(f"game_updates:{game.link}", f"unit_pp_updated:{gu.id}")
            return {
                "ok": True, 
                "unit_id": gu.id, 
                "move_pp": gu.move_pp,
                "targets": damage_results, 
                "missed_target_ids": missed_target_ids,
                "removed_ids": removed_ids
            }

    attacker_removed = gu.id in removed_ids
    if not attacker_removed:
        gu.can_move = False
        db.flush()
    remaining_units = db.query(GameUnit).filter(
        GameUnit.game_id == game.id,
        GameUnit.user_id == current_player_id,
        GameUnit.can_move == True
    ).count()

    end_turn_removed_ids: List[int] = []

    if remaining_units == 0:
        units_to_sync = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
        for unit in units_to_sync:
            unit.starting_x = unit.current_x
            unit.starting_y = unit.current_y

        # Resolve end-of-turn status damage for the current player before advancing.
        end_turn_modified_unit_ids = set(apply_end_of_turn_status_damage(current_player_id, game.id, db))
        should_apply_round_weather = ((state.current_turn + 1) % len(state.players)) == 0
        if should_apply_round_weather:
            end_turn_modified_unit_ids.update(apply_end_of_round_weather_damage(game.id, db))
            end_turn_modified_unit_ids.update(apply_end_of_round_entry_hazard_effects(game.id, state.current_turn, db))
            decrement_and_expire_hazards(game.id, db)

        end_turn_removed_ids = remove_fainted_units_from_play(game.id, db)
        if end_turn_removed_ids:
            removed_ids = list(set(removed_ids + end_turn_removed_ids))

        remaining_units_after_end_turn_damage = db.query(GameUnit).filter(GameUnit.game_id == game.id).all()
        remaining_players_after_end_turn_damage = {unit.user_id for unit in remaining_units_after_end_turn_damage}
        if len(remaining_players_after_end_turn_damage) == 1:
            state.status = GameStatus.completed
            state.winner_id = next(iter(remaining_players_after_end_turn_damage))
            winner_name = get_username_by_id(state.winner_id, db)
            publish_system_log_event(game.link, f"{winner_name} won", state, db)
            db.commit()
            for unit_id in removed_ids:
                redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
            redis_client.publish(f"game_updates:{game.link}", "game_completed")
            redis_client.publish(f"game_updates:{game.link}", f"unit_pp_updated:{gu.id}")
            return {
                "ok": True,
                "unit_id": gu.id,
                "move_pp": gu.move_pp,
                "targets": damage_results,
                "missed_target_ids": missed_target_ids,
                "removed_ids": removed_ids,
            }

        current_player_units = db.query(GameUnit).filter(
            GameUnit.game_id == game.id,
            GameUnit.user_id == current_player_id
        ).all()
        for unit in current_player_units:
            unit.can_move = True

        playable_players, _, completed_now = set_next_playable_turn_after_current(game, state, current_player_id, db)
        if completed_now:
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_completed")
            redis_client.publish(f"game_updates:{game.link}", f"unit_pp_updated:{gu.id}")
            return {
                "ok": True,
                "unit_id": gu.id,
                "move_pp": gu.move_pp,
                "targets": damage_results,
                "missed_target_ids": missed_target_ids,
                "removed_ids": removed_ids,
            }
        if not playable_players:
            raise HTTPException(status_code=400, detail="Invalid game state")

        # Decrement and expire stat boosts/statuses for the new current player's units.
        new_current_player_id = playable_players[state.current_turn % len(playable_players)]
        modified_unit_ids = set(end_turn_modified_unit_ids)
        modified_unit_ids.update(decrement_and_expire_stat_boosts(new_current_player_id, game.id, db))
        modified_unit_ids.update(
            decrement_and_expire_status_effects(new_current_player_id, game.id, db, game, state)
        )
        removed_ids.extend(remove_fainted_units_from_play(game.id, db))
        
        # Broadcast stat updates for units that had boosts expire
        for unit_id in modified_unit_ids:
            redis_client.publish(f"game_updates:{game.link}", f"unit_stats_updated:{unit_id}")

        if game.max_turns and state.current_turn >= game.max_turns * len(state.players):
            state.status = GameStatus.completed
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "game_completed")
        else:
            now = datetime.now(timezone.utc)
            state.turn_deadline = now + timedelta(seconds=game.turn_seconds)
            compute_turn_locks(game, state, db)
            publish_turn_start_logs(game, state, db)
            db.commit()
            redis_client.publish(f"game_updates:{game.link}", "turn_advanced")
            redis_client.publish(f"game_updates:{game.link}", "turn_started")
    else:
        db.commit()

    redis_client.publish(f"game_updates:{game.link}", "unit_locked")
    for unit_id in removed_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{unit_id}")
    
    # Broadcast PP update
    redis_client.publish(f"game_updates:{game.link}", f"unit_pp_updated:{gu.id}")
    
    return {
        "ok": True, 
        "unit_id": gu.id, 
        "move_pp": gu.move_pp,
        "targets": damage_results, 
        "missed_target_ids": missed_target_ids,
        "removed_ids": removed_ids
    }

@router.post("/{link}/wait")
def wait_unit(
    link: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        unit_id = int(payload.get("unit_id"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.in_progress:
        raise HTTPException(status_code=400, detail="Game not in progress")

    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        raise HTTPException(status_code=400, detail="Game completed")

    if not playable_players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")

    current_player_id = playable_players[state.current_turn % len(playable_players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    gu = db.query(GameUnit).filter(GameUnit.id == unit_id, GameUnit.game_id == game.id).first()
    if not gu:
        raise HTTPException(status_code=404, detail="Unit not found")
    if gu.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only wait with your own unit")
    if not gu.can_move:
        raise HTTPException(status_code=400, detail="Unit is locked")

    gu.can_move = False
    db.flush()

    removed_ids, turn_advanced, game_completed = advance_turn_if_player_has_no_actions(
        game, state, current_player_id, db
    )
    if not turn_advanced and not game_completed:
        db.commit()

    redis_client.publish(f"game_updates:{game.link}", "unit_locked")
    for rid in removed_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{rid}")

    return {
        "ok": True,
        "unit_id": gu.id,
        "turn_advanced": turn_advanced,
        "game_completed": game_completed,
        "removed_ids": removed_ids,
    }


@router.post("/{link}/pick_up_item")
def pick_up_map_item(
    link: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        unit_id = int(payload.get("unit_id"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.in_progress:
        raise HTTPException(status_code=400, detail="Game not in progress")

    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        raise HTTPException(status_code=400, detail="Game completed")

    if not playable_players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")

    current_player_id = playable_players[state.current_turn % len(playable_players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    gu = db.query(GameUnit).filter(GameUnit.id == unit_id, GameUnit.game_id == game.id).first()
    if not gu:
        raise HTTPException(status_code=404, detail="Unit not found")
    if gu.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only pick up items with your own unit")
    if not gu.can_move:
        raise HTTPException(status_code=400, detail="Unit is locked")

    map_state = _get_or_create_game_map_state(game, db)
    x = int(gu.current_x)
    y = int(gu.current_y)
    tiles = map_state.item_id_tiles
    if not isinstance(tiles, list) or y < 0 or y >= len(tiles):
        raise HTTPException(status_code=400, detail="No item on this tile")
    row = tiles[y]
    if not isinstance(row, list) or x < 0 or x >= len(row):
        raise HTTPException(status_code=400, detail="No item on this tile")

    item_id = row[x]
    if not isinstance(item_id, int) or item_id <= 0:
        raise HTTPException(status_code=400, detail="No item on this tile")

    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    old_held_slug = get_unit_held_item(gu)
    swapped = bool(old_held_slug)
    dropped_item_id: int | None = None
    if swapped:
        old_item = resolve_item_record(old_held_slug, db)
        if not old_item:
            raise HTTPException(status_code=400, detail="Held item is invalid")
        dropped_item_id = old_item.id

    new_tiles = [list(r) if isinstance(r, list) else [] for r in tiles]
    new_tiles[y][x] = dropped_item_id
    map_state.item_id_tiles = new_tiles
    db.add(map_state)

    set_unit_held_item(gu, item.slug, db)
    unit_info = db.query(Unit).filter_by(id=gu.unit_id).first()
    if unit_info:
        sync_tm_move_pp(gu, unit_info, db)

    clear_movement_locked(game.link, gu.id)
    gu.can_move = False
    db.flush()

    if swapped and old_held_slug:
        old_item_name = resolve_held_item_name(old_held_slug, db) or old_held_slug
        publish_system_log_event(
            game.link,
            f"{get_unit_display_name(gu, db)} swapped {old_item_name} for {item.name}",
            state,
            db,
        )
    else:
        publish_system_log_event(
            game.link,
            f"{get_unit_display_name(gu, db)} picked up {item.name}",
            state,
            db,
        )

    removed_ids, turn_advanced, game_completed = advance_turn_if_player_has_no_actions(
        game, state, current_player_id, db
    )
    if not turn_advanced and not game_completed:
        db.commit()

    attach_game_unit_loadout_fields(gu, db)

    redis_client.publish(f"game_updates:{game.link}", "unit_locked")
    if swapped and dropped_item_id is not None:
        redis_client.publish(
            f"game_updates:{game.link}",
            f"map_item_swapped:{x}:{y}:{dropped_item_id}",
        )
    else:
        redis_client.publish(f"game_updates:{game.link}", f"map_item_picked:{x}:{y}")
    redis_client.publish(f"game_updates:{game.link}", f"unit_item_updated:{gu.id}")
    for rid in removed_ids:
        redis_client.publish(f"game_updates:{game.link}", f"unit_removed:{rid}")
    if turn_advanced:
        redis_client.publish(f"game_updates:{game.link}", "turn_advanced")
        redis_client.publish(f"game_updates:{game.link}", "turn_started")
    if game_completed:
        redis_client.publish(f"game_updates:{game.link}", "game_completed")

    return {
        "ok": True,
        "unit_id": gu.id,
        "item_slug": item.slug,
        "item_name": item.name,
        "swapped": swapped,
        "dropped_item_id": dropped_item_id,
        "x": x,
        "y": y,
        "held_item": gu.held_item,
        "held_item_slug": gu.held_item_slug,
        "held_tm_move_id": gu.held_tm_move_id,
        "move_pp": gu.move_pp,
        "turn_advanced": turn_advanced,
        "game_completed": game_completed,
        "removed_ids": removed_ids,
    }


@router.post("/{link}/revert_position")
def revert_unit_position(
    link: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        unit_id = int(payload.get("unit_id"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    game = db.query(Game).filter(Game.link == link).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    state = db.query(GameState).filter_by(game_id=game.id).first()
    if not state or state.status != GameStatus.in_progress:
        raise HTTPException(status_code=400, detail="Game not in progress")

    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        raise HTTPException(status_code=400, detail="Game completed")

    if not playable_players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")

    current_player_id = playable_players[state.current_turn % len(playable_players)]
    if current_player_id != user.id:
        raise HTTPException(status_code=403, detail="Not your turn")

    gu = db.query(GameUnit).filter(GameUnit.id == unit_id, GameUnit.game_id == game.id).first()
    if not gu:
        raise HTTPException(status_code=404, detail="Unit not found")
    if gu.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only revert your own unit")
    if not gu.can_move:
        raise HTTPException(status_code=400, detail="Unit has already acted")

    if gu.current_x == gu.starting_x and gu.current_y == gu.starting_y:
        clear_movement_locked(game.link, gu.id)
        return {
            "ok": True,
            "unit_id": gu.id,
            "x": gu.current_x,
            "y": gu.current_y,
            "reverted": False,
        }

    gu.current_x = gu.starting_x
    gu.current_y = gu.starting_y
    clear_movement_locked(game.link, gu.id)
    db.commit()

    redis_client.publish(
        f"game_updates:{game.link}",
        f"unit_moved:{gu.id}:{gu.user_id}:{gu.current_x}:{gu.current_y}",
    )

    return {
        "ok": True,
        "unit_id": gu.id,
        "x": gu.current_x,
        "y": gu.current_y,
        "reverted": True,
    }


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
    playable_players, _, completed_now = reconcile_playable_players(game, state, db)
    if completed_now:
        db.commit()
        redis_client.publish(f"game_updates:{game.link}", "game_completed")
        raise HTTPException(status_code=400, detail="Game completed")

    if not playable_players or state.current_turn is None:
        raise HTTPException(status_code=400, detail="Invalid game state")
    current_player_id = playable_players[state.current_turn % len(playable_players)]
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
    if is_movement_locked(game.link, gu.id):
        raise HTTPException(status_code=400, detail="Unit has already moved")

    # Prevent movement if Immobilized state is active (does not affect using moves)
    try:
        gu_state = normalize_states(gu.states)
        if gu_state and gu_state[0] == "immobilized" and int(gu_state[1]) > 0:
            raise HTTPException(status_code=400, detail="Unit is immobilized and cannot move")
    except HTTPException:
        raise
    except Exception:
        pass

    map_obj = db.query(Map).filter_by(id=game.map_id).first()
    if x < 0 or y < 0 or x >= map_obj.width or y >= map_obj.height:
        raise HTTPException(status_code=400, detail="Out of bounds")

    key = f"turnlock:{game.link}:{user.id}"
    lock = redis_client.hget(key, str(gu.id))
    if not lock:
        raise HTTPException(status_code=400, detail="Move set not initialized")
    lock = json.loads(lock)
    allowed = {(tx, ty) for tx, ty in lock["tiles"]}
    if (x, y) not in allowed:
        raise HTTPException(status_code=400, detail="Illegal move for this turn")

    special_tiles = map_obj.tile_data.get("special_tiles")
    unit_types = get_unit_types(gu, db)
    ability_names = get_unit_ability_names(gu, db)
    if not unit_can_occupy_tile(special_tiles, x, y, unit_types, ability_names):
        raise HTTPException(status_code=400, detail="This unit cannot move onto this tile")

    occupied_tiles = {
        (unit.current_x, unit.current_y)
        for unit in db.query(GameUnit)
        .filter(GameUnit.game_id == game.id, GameUnit.id != gu.id, GameUnit.current_hp > 0)
        .all()
    }
    enemy_blocked_tiles = occupied_tiles if not unit_can_pass_through_units(unit_types) else set()

    base_costs = map_obj.tile_data["movement_cost"]
    effective_costs = build_movement_cost_grid(
        base_costs,
        special_tiles,
        unit_types,
        ability_names,
    )
    final_x, final_y, slid = resolve_movement_destination(
        gu.current_x,
        gu.current_y,
        x,
        y,
        effective_costs,
        special_tiles,
        map_obj.width,
        map_obj.height,
        unit_types,
        ability_names,
        blocked_tiles=enemy_blocked_tiles,
        occupied_tiles=occupied_tiles,
    )

    if (final_x, final_y) in occupied_tiles:
        raise HTTPException(status_code=400, detail="Tile occupied")
    if not unit_can_occupy_tile(special_tiles, final_x, final_y, unit_types, ability_names):
        raise HTTPException(status_code=400, detail="This unit cannot move onto this tile")

    gu.current_x = final_x
    gu.current_y = final_y
    movement_locked = slid
    if movement_locked:
        set_movement_locked(game.link, gu.id)
    db.commit()

    redis_client.publish(
        f"game_updates:{game.link}",
        f"unit_moved:{gu.id}:{gu.user_id}:{final_x}:{final_y}"
    )

    return {
        "ok": True,
        "unit_id": gu.id,
        "x": final_x,
        "y": final_y,
        "requested_x": x,
        "requested_y": y,
        "slid": slid,
        "movement_locked": movement_locked,
    }

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