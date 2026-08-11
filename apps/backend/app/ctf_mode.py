"""Capture The Flag mode: flags, per-player jails, and win conditions."""

from __future__ import annotations

import math
import re
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Game, GameMapState, GameState, GameUnit

UNLOCK_MAX_HP = 20
CTF_JAIL_TILE = "ctf_jail"
CTF_UNLOCK_TILE = "ctf_unlock"
CTF_JAIL_PATTERN = re.compile(r"^ctf_jail(?:_p([1-8]))?$", re.IGNORECASE)
OMNIBOOST_EXPIRES_TURNS = 3
OMNIBOOST_STATS = ("attack", "defense", "sp_attack", "sp_defense", "speed")


def is_ctf_game(game: Game) -> bool:
    value = getattr(game.gamemode, "value", None) or str(game.gamemode)
    return value == "Capture The Flag"


def get_player_number(player_order: list[int], user_id: int) -> int | None:
    try:
        return list(player_order).index(int(user_id)) + 1
    except ValueError:
        return None


def _empty_grid(height: int, width: int, fill=None):
    return [[fill for _ in range(width)] for _ in range(height)]


def make_flag_cell(owner: int) -> dict:
    return {"owner": int(owner)}


def encode_jail_tile(owner: int) -> str:
    return f"{CTF_JAIL_TILE}_p{int(owner)}"


def parse_jail_tile(value: Any) -> int | None:
    """Return the jail owner player number, or None if the cell is not an owned jail."""
    if not isinstance(value, str):
        return None
    match = CTF_JAIL_PATTERN.match(value.strip())
    if not match:
        return None
    owner_raw = match.group(1)
    if owner_raw is None:
        return None
    return int(owner_raw)


def is_jail_tile(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return CTF_JAIL_PATTERN.match(value.strip()) is not None


def make_unlock_cell() -> dict:
    return {
        "kind": "unlock",
        "hp": UNLOCK_MAX_HP,
        "max_hp": UNLOCK_MAX_HP,
    }


def build_flag_tiles_from_map(map_obj, existing: list | None = None) -> list[list[dict | None]]:
    height = int(map_obj.height)
    width = int(map_obj.width)
    grid = _empty_grid(height, width, None)
    tile_data = map_obj.tile_data if isinstance(map_obj.tile_data, dict) else {}
    flags = tile_data.get("flags")
    if not isinstance(flags, list):
        return existing if isinstance(existing, list) and existing else grid

    for y in range(min(height, len(flags))):
        row = flags[y]
        if not isinstance(row, list):
            continue
        for x in range(min(width, len(row))):
            value = row[x]
            if value is None:
                continue
            try:
                owner = int(value)
            except (TypeError, ValueError):
                continue
            if owner < 0:
                continue
            # 0 = neutral, 1-8 = starting owner
            if owner > 8:
                continue
            grid[y][x] = make_flag_cell(owner)
    return grid


def build_unlock_tiles_from_map(map_obj, existing: list | None = None) -> list[list[dict | None]]:
    """Unlock tiles are retired; keep an empty grid for leftover map-state rows."""
    height = int(getattr(map_obj, "height", 0) or 0)
    width = int(getattr(map_obj, "width", 0) or 0)
    if height <= 0 or width <= 0:
        return existing if isinstance(existing, list) and existing else []
    return _empty_grid(height, width, None)


def list_jails(map_obj) -> list[tuple[int, int, int]]:
    """Return (x, y, owner_player_number) for each owned jail tile."""
    tile_data = map_obj.tile_data if isinstance(map_obj.tile_data, dict) else {}
    special = tile_data.get("special_tiles")
    out: list[tuple[int, int, int]] = []
    if not isinstance(special, list):
        return out
    for y, row in enumerate(special):
        if not isinstance(row, list):
            continue
        for x, cell in enumerate(row):
            owner = parse_jail_tile(cell)
            if owner is not None:
                out.append((x, y, owner))
    return out


def list_jail_tiles(map_obj) -> list[tuple[int, int]]:
    """Legacy helper: jail coordinates only (owned jails)."""
    return [(x, y) for x, y, _owner in list_jails(map_obj)]


def get_jail_at(map_obj, x: int, y: int) -> dict | None:
    tile_data = map_obj.tile_data if isinstance(getattr(map_obj, "tile_data", None), dict) else {}
    special = tile_data.get("special_tiles")
    if not isinstance(special, list) or y < 0 or y >= len(special):
        return None
    row = special[y]
    if not isinstance(row, list) or x < 0 or x >= len(row):
        return None
    owner = parse_jail_tile(row[x])
    if owner is None:
        return None
    return {"x": int(x), "y": int(y), "owner": owner}


def get_jail_tile_for_player(map_obj, player_number: int) -> tuple[int, int] | None:
    for x, y, owner in list_jails(map_obj):
        if owner == int(player_number):
            return (x, y)
    return None


def mark_flag_tiles_dirty(map_state: GameMapState) -> None:
    flag_modified(map_state, "flag_tiles")


def mark_unlock_tiles_dirty(map_state: GameMapState) -> None:
    flag_modified(map_state, "unlock_tiles")


def get_flag_at(flag_tiles: list | None, x: int, y: int) -> dict | None:
    if not isinstance(flag_tiles, list) or y < 0 or y >= len(flag_tiles):
        return None
    row = flag_tiles[y]
    if not isinstance(row, list) or x < 0 or x >= len(row):
        return None
    cell = row[x]
    return cell if isinstance(cell, dict) else None


def get_unlock_at(unlock_tiles: list | None, x: int, y: int) -> dict | None:
    if not isinstance(unlock_tiles, list) or y < 0 or y >= len(unlock_tiles):
        return None
    row = unlock_tiles[y]
    if not isinstance(row, list) or x < 0 or x >= len(row):
        return None
    cell = row[x]
    return cell if isinstance(cell, dict) else None


def capture_damage(capturer_current_hp: int, capturer_max_hp: int) -> int:
    max_hp = max(1, int(capturer_max_hp or 1))
    cur = max(0, int(capturer_current_hp or 0))
    return max(1, int(math.ceil((cur / max_hp) * 10)))


def apply_unlock_damage(cell: dict, capturer_current_hp: int, capturer_max_hp: int) -> bool:
    """Legacy HP-unlock helper kept for existing unit tests."""
    damage = capture_damage(capturer_current_hp, capturer_max_hp)
    max_hp = int(cell.get("max_hp") or UNLOCK_MAX_HP)
    hp = int(cell.get("hp") or max_hp)
    new_hp = hp - damage
    if new_hp <= 0:
        cell["hp"] = max_hp
        return True
    cell["hp"] = new_hp
    return False


def count_flags_by_owner(flag_tiles: list | None) -> dict[int, int]:
    counts: dict[int, int] = {}
    if not isinstance(flag_tiles, list):
        return counts
    for row in flag_tiles:
        if not isinstance(row, list):
            continue
        for cell in row:
            if not isinstance(cell, dict):
                continue
            owner = int(cell.get("owner") or 0)
            if owner <= 0:
                continue
            counts[owner] = counts.get(owner, 0) + 1
    return counts


def total_flag_count(flag_tiles: list | None) -> int:
    total = 0
    if not isinstance(flag_tiles, list):
        return 0
    for row in flag_tiles:
        if not isinstance(row, list):
            continue
        for cell in row:
            if isinstance(cell, dict):
                total += 1
    return total


def player_owns_all_flags(flag_tiles: list | None, player_number: int) -> bool:
    total = total_flag_count(flag_tiles)
    if total <= 0:
        return False
    counts = count_flags_by_owner(flag_tiles)
    return counts.get(int(player_number), 0) == total


def is_unit_jailed(unit: GameUnit) -> bool:
    flags = getattr(unit, "flags", None)
    if not isinstance(flags, dict):
        return False
    return bool(flags.get("jailed"))


def get_unit_jailed_by(unit: GameUnit) -> int | None:
    flags = getattr(unit, "flags", None)
    if not isinstance(flags, dict):
        return None
    raw = flags.get("jailed_by")
    if raw is None:
        return None
    try:
        owner = int(raw)
    except (TypeError, ValueError):
        return None
    return owner if 1 <= owner <= 8 else None


def set_unit_jailed(
    unit: GameUnit,
    jailed: bool,
    db: Session,
    *,
    jailed_by: int | None = None,
) -> None:
    flags = dict(getattr(unit, "flags", None) or {})
    if jailed:
        flags["jailed"] = True
        if jailed_by is not None:
            flags["jailed_by"] = int(jailed_by)
    else:
        flags.pop("jailed", None)
        flags.pop("jailed_by", None)
    unit.flags = flags
    flag_modified(unit, "flags")
    db.add(unit)


def unit_blocks_occupation(unit: GameUnit) -> bool:
    if int(getattr(unit, "current_hp", 0) or 0) <= 0:
        return False
    if int(getattr(unit, "current_x", -1) or -1) < 0:
        return False
    if int(getattr(unit, "current_y", -1) or -1) < 0:
        return False
    if is_unit_jailed(unit):
        return False
    return True


def pick_jail_tile(
    jail_tiles: list[tuple[int, int]],
    occupied: set[tuple[int, int]],
) -> tuple[int, int] | None:
    if not jail_tiles:
        return None
    for tile in jail_tiles:
        if tile not in occupied:
            return tile
    return jail_tiles[0]


def get_match_start(unit: GameUnit) -> tuple[int, int]:
    start_x = getattr(unit, "match_start_x", None)
    start_y = getattr(unit, "match_start_y", None)
    if start_x is not None and start_y is not None:
        return (int(start_x), int(start_y))
    return (int(unit.starting_x), int(unit.starting_y))


def set_match_start(unit: GameUnit, x: int, y: int) -> None:
    unit.match_start_x = int(x)
    unit.match_start_y = int(y)


def nearest_open_tile(
    origin: tuple[int, int],
    occupied: set[tuple[int, int]],
    width: int,
    height: int,
) -> tuple[int, int]:
    ox, oy = origin
    if 0 <= ox < width and 0 <= oy < height and origin not in occupied:
        return origin
    max_radius = max(width, height) + 1
    for radius in range(1, max_radius):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = ox + dx, oy + dy
                if 0 <= x < width and 0 <= y < height and (x, y) not in occupied:
                    return (x, y)
    return origin


def resolve_jailer_user_id(fainted: GameUnit, db: Session, game_state: GameState | None) -> int | None:
    """Player who should receive this unit in their jail."""
    flags = getattr(fainted, "flags", None) or {}
    attacker_id = flags.get("last_damage_attacker_id") if isinstance(flags, dict) else None
    if attacker_id is not None:
        attacker = db.query(GameUnit).filter(GameUnit.id == int(attacker_id)).first()
        if attacker is not None and int(attacker.user_id) != int(fainted.user_id):
            return int(attacker.user_id)
    if game_state and game_state.players and game_state.current_turn is not None:
        players = list(game_state.players)
        if players:
            current = int(players[int(game_state.current_turn) % len(players)])
            if current != int(fainted.user_id):
                return current
    return None


def apply_omniboost(unit: GameUnit, db: Session) -> None:
    """Raise all battle stats (not HP) by 1 stage for 3 turns."""
    boosts = getattr(unit, "stat_boosts", None)
    if not isinstance(boosts, dict):
        boosts = {}
    next_boosts = dict(boosts)
    for stat in OMNIBOOST_STATS:
        instances = list(next_boosts.get(stat) or [])
        instances.append({"magnitude": 1, "expires_turn": OMNIBOOST_EXPIRES_TURNS})
        next_boosts[stat] = instances
    unit.stat_boosts = next_boosts
    flag_modified(unit, "stat_boosts")
    db.add(unit)


def free_units_held_in_jail(
    game_id: int,
    jail_owner: int,
    map_obj,
    db: Session,
) -> list[GameUnit]:
    """Free every unit held in a player's jail and return them to match-start tiles."""
    units = db.query(GameUnit).filter(GameUnit.game_id == game_id).all()
    jail_tile = get_jail_tile_for_player(map_obj, jail_owner)
    occupied = {
        (int(unit.current_x), int(unit.current_y))
        for unit in units
        if unit_blocks_occupation(unit)
    }
    width = int(getattr(map_obj, "width", 0) or 0)
    height = int(getattr(map_obj, "height", 0) or 0)
    freed: list[GameUnit] = []
    for unit in units:
        if not is_unit_jailed(unit):
            continue
        held_by = get_unit_jailed_by(unit)
        on_this_jail = (
            jail_tile is not None
            and (int(unit.current_x), int(unit.current_y)) == jail_tile
        )
        if held_by != int(jail_owner) and not on_this_jail:
            continue
        set_unit_jailed(unit, False, db)
        unit.can_move = True
        unit.is_fainted = False
        if int(unit.current_hp or 0) <= 0:
            max_hp = int((unit.current_stats or {}).get("hp") or 1)
            unit.current_hp = max_hp
        dest = nearest_open_tile(get_match_start(unit), occupied, width, height)
        unit.current_x, unit.current_y = dest
        unit.starting_x, unit.starting_y = dest
        occupied.add(dest)
        apply_omniboost(unit, db)
        freed.append(unit)
    return freed


def free_jailed_units_for_player(
    game_id: int,
    user_id: int,
    db: Session,
    *,
    spawn_tiles: list[tuple[int, int]] | None = None,
) -> list[GameUnit]:
    """Legacy helper: free one owner's jailed units. Prefer free_units_held_in_jail."""
    units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game_id, GameUnit.user_id == user_id)
        .all()
    )
    freed: list[GameUnit] = []
    spawn_idx = 0
    for unit in units:
        if not is_unit_jailed(unit):
            continue
        set_unit_jailed(unit, False, db)
        unit.can_move = True
        unit.is_fainted = False
        if int(unit.current_hp or 0) <= 0:
            max_hp = int((unit.current_stats or {}).get("hp") or 1)
            unit.current_hp = max_hp
        if spawn_tiles:
            tile = spawn_tiles[spawn_idx % len(spawn_tiles)]
            spawn_idx += 1
            unit.current_x, unit.current_y = tile
            unit.starting_x, unit.starting_y = tile
        apply_omniboost(unit, db)
        freed.append(unit)
    return freed


def all_units_jailed_for_player(game_id: int, user_id: int, db: Session) -> bool:
    units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game_id, GameUnit.user_id == user_id)
        .all()
    )
    living = [u for u in units if not u.is_fainted]
    if not living:
        return True
    return all(is_unit_jailed(u) for u in living)


def ctf_playable_player_ids(state: GameState, game_id: int, db: Session) -> list[int]:
    """Players who still have at least one non-jailed unit."""
    order = list(state.players or [])
    playable: list[int] = []
    for pid in order:
        units = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id == pid,
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        if any(not is_unit_jailed(u) and int(u.current_hp or 0) > 0 for u in units):
            playable.append(int(pid))
    return playable


def leading_flag_owners(flag_tiles: list | None, player_order: list[int]) -> list[int]:
    """Return user ids with the most flags (ties included)."""
    counts = count_flags_by_owner(flag_tiles)
    if not counts:
        return list(player_order)
    best = max(counts.values())
    leaders: list[int] = []
    for index, user_id in enumerate(player_order):
        player_number = index + 1
        if counts.get(player_number, 0) == best:
            leaders.append(int(user_id))
    return leaders or list(player_order)
