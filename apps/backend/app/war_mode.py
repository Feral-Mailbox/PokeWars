"""War game mode: objective tiles, income, summoning, and capture."""

from __future__ import annotations

import math
import re
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Game, GameMapState, GamePlayer, GameState, GameUnit

POKEBALL_MAX_HP = 20
OBJECTIVE_TILE_PATTERN = re.compile(r"^(pokeball|master_ball)(?:_p(\d+))?$")


def is_war_game(game: Game) -> bool:
    return str(game.gamemode) == "War" or getattr(game.gamemode, "value", None) == "War"


def get_player_number(player_order: list[int], user_id: int) -> int | None:
    try:
        return player_order.index(int(user_id)) + 1
    except ValueError:
        return None


def get_current_round(state: GameState) -> int:
    players = list(state.players or [])
    if not players or state.current_turn is None:
        return 1
    return (int(state.current_turn) // len(players)) + 1


def parse_objective_from_special_tile(cell: Any) -> tuple[str, int] | None:
    if not isinstance(cell, str):
        return None
    value = cell.strip().lower()
    if not value:
        return None
    match = OBJECTIVE_TILE_PATTERN.match(value)
    if not match:
        return None
    kind = match.group(1)
    owner = int(match.group(2)) if match.group(2) else 0
    return kind, owner


def is_objective_special_tile(cell: Any) -> bool:
    return parse_objective_from_special_tile(cell) is not None


def make_objective_cell(kind: str, owner: int, *, last_summon_round: int | None = None) -> dict:
    cell = {
        "kind": kind,
        "owner": int(owner),
        "hp": POKEBALL_MAX_HP,
        "max_hp": POKEBALL_MAX_HP,
        "last_summon_round": last_summon_round,
    }
    if kind == "master_ball" and owner > 0:
        cell["original_owner"] = int(owner)
    return cell


def build_empty_objective_grid(height: int, width: int) -> list[list[dict | None]]:
    return [[None for _ in range(width)] for _ in range(height)]


def _find_spawn_center(spawn_points: list | None, player_number: int) -> tuple[int, int] | None:
    if not spawn_points:
        return None
    coords: list[tuple[int, int]] = []
    for y, row in enumerate(spawn_points):
        if not isinstance(row, list):
            continue
        for x, value in enumerate(row):
            if value == player_number:
                coords.append((x, y))
    if not coords:
        return None
    avg_x = round(sum(c[0] for c in coords) / len(coords))
    avg_y = round(sum(c[1] for c in coords) / len(coords))
    return avg_x, avg_y


def build_objective_tiles_from_map(
    map_obj,
    player_order: list[int],
    existing: list[list[dict | None]] | None = None,
) -> list[list[dict | None]]:
    height = map_obj.height
    width = map_obj.width
    grid = build_empty_objective_grid(height, width)
    tile_data = map_obj.tile_data if isinstance(map_obj.tile_data, dict) else {}
    special_tiles = tile_data.get("special_tiles")
    spawn_points = tile_data.get("spawn_points")

    if isinstance(special_tiles, list):
        for y, row in enumerate(special_tiles):
            if not isinstance(row, list):
                continue
            for x, cell in enumerate(row):
                parsed = parse_objective_from_special_tile(cell)
                if parsed is None:
                    continue
                kind, owner = parsed
                grid[y][x] = make_objective_cell(kind, owner)

    players_with_master = {
        cell["owner"]
        for row in grid
        for cell in row
        if cell and cell.get("kind") == "master_ball" and int(cell.get("owner") or 0) > 0
    }
    for index in range(len(player_order)):
        player_number = index + 1
        if player_number in players_with_master:
            continue
        center = _find_spawn_center(spawn_points, player_number)
        if center is None:
            continue
        x, y = center
        if 0 <= y < height and 0 <= x < width and grid[y][x] is None:
            grid[y][x] = make_objective_cell("master_ball", player_number)

    if existing:
        for y, row in enumerate(existing):
            if y >= height or not isinstance(row, list):
                continue
            for x, cell in enumerate(row):
                if x >= width or not isinstance(cell, dict) or grid[y][x] is None:
                    continue
                current = grid[y][x]
                if current is None:
                    continue
                current["hp"] = int(cell.get("hp", current["hp"]))
                current["owner"] = int(cell.get("owner", current["owner"]))
                current["last_summon_round"] = cell.get("last_summon_round")

    return grid


def get_objective_at(grid: list[list[dict | None]] | None, x: int, y: int) -> dict | None:
    if not grid or y < 0 or x < 0 or y >= len(grid):
        return None
    row = grid[y]
    if not isinstance(row, list) or x >= len(row):
        return None
    cell = row[x]
    return cell if isinstance(cell, dict) else None


def count_owned_objectives(grid: list[list[dict | None]] | None, player_number: int) -> int:
    if not grid or player_number <= 0:
        return 0
    total = 0
    for row in grid:
        if not isinstance(row, list):
            continue
        for cell in row:
            if isinstance(cell, dict) and int(cell.get("owner") or 0) == player_number:
                total += 1
    return total


def calculate_war_income(game: Game, grid: list[list[dict | None]] | None, player_number: int) -> int:
    base = int(game.cash_per_turn or 0)
    if base <= 0:
        return 0
    owned = count_owned_objectives(grid, player_number)
    return base * owned


def apply_war_round_income(game: Game, state: GameState, map_state: GameMapState, db: Session) -> None:
    if not is_war_game(game):
        return
    grid = map_state.objective_tiles
    if not grid:
        return
    player_order = list(state.players or [])
    for user_id in player_order:
        player_number = get_player_number(player_order, int(user_id))
        if player_number is None:
            continue
        income = calculate_war_income(game, grid, player_number)
        if income <= 0:
            continue
        player_state = (
            db.query(GamePlayer)
            .filter_by(game_id=game.id, player_id=int(user_id))
            .first()
        )
        if player_state:
            player_state.cash_remaining = int(player_state.cash_remaining or 0) + income


def compute_capture_damage(capturer_current_hp: int, capturer_max_hp: int) -> int:
    if capturer_max_hp <= 0:
        return 1
    return max(1, math.ceil((capturer_current_hp / capturer_max_hp) * 10))


def get_capturer_hp_stats(capturer_current_hp: int, capturer_max_hp: int) -> tuple[int, int]:
    current_hp = max(0, int(capturer_current_hp or 0))
    max_hp = int(capturer_max_hp or 0)
    if max_hp <= 0:
        max_hp = max(current_hp, 1)
    return current_hp, max_hp


def restore_objective_hp(cell: dict) -> None:
    cell["hp"] = int(cell.get("max_hp", POKEBALL_MAX_HP))


def player_owns_master_ball(grid: list[list[dict | None]] | None, player_number: int) -> bool:
    if not grid or player_number <= 0:
        return False
    for row in grid:
        if not isinstance(row, list):
            continue
        for cell in row:
            if (
                isinstance(cell, dict)
                and cell.get("kind") == "master_ball"
                and int(cell.get("owner") or 0) == player_number
            ):
                return True
    return False


def get_master_ball_original_owner(cell: dict) -> int | None:
    """Player number that originally had this master ball (from map tile suffix)."""
    if cell.get("kind") != "master_ball":
        return None
    original = cell.get("original_owner")
    if original is not None:
        return int(original)
    return int(cell.get("owner") or 0) or None


def mark_master_ball_original_owners(grid: list[list[dict | None]] | None) -> None:
    if not grid:
        return
    for row in grid:
        if not isinstance(row, list):
            continue
        for cell in row:
            if isinstance(cell, dict) and cell.get("kind") == "master_ball":
                if cell.get("original_owner") is None:
                    cell["original_owner"] = int(cell.get("owner") or 0)


def can_summon_on_objective(cell: dict, player_number: int, current_round: int) -> bool:
    if int(cell.get("owner") or 0) != player_number:
        return False
    last_round = cell.get("last_summon_round")
    return last_round is None or int(last_round) < current_round


def can_capture_objective(cell: dict, player_number: int) -> bool:
    owner = int(cell.get("owner") or 0)
    return owner != player_number


def mark_objective_tiles_dirty(map_state: GameMapState) -> None:
    """Nested dict edits inside objective_tiles are not tracked unless flagged."""
    flag_modified(map_state, "objective_tiles")


def restore_objectives_for_units(map_state: GameMapState, units: list) -> bool:
    changed = False
    for unit in units:
        x = int(getattr(unit, "current_x", 0))
        y = int(getattr(unit, "current_y", 0))
        if handle_unit_left_objective_tile(map_state, x, y):
            changed = True
    if changed:
        mark_objective_tiles_dirty(map_state)
    return changed


def restore_unoccupied_damaged_objectives(
    map_state: GameMapState,
    game_id: int,
    db: Session,
) -> list[tuple[int, int, dict]]:
    """Restore capture progress on damaged objectives with no unit standing on them."""
    grid = map_state.objective_tiles
    if not grid:
        return []

    occupied_tiles = {
        (int(unit.current_x), int(unit.current_y))
        for unit in db.query(GameUnit)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.is_fainted == False,
            GameUnit.current_hp > 0,
        )
        .all()
    }

    restored: list[tuple[int, int, dict]] = []
    for y, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        for x, cell in enumerate(row):
            if not isinstance(cell, dict):
                continue
            max_hp = int(cell.get("max_hp", POKEBALL_MAX_HP))
            hp = int(cell.get("hp", max_hp))
            if hp >= max_hp:
                continue
            if (x, y) in occupied_tiles:
                continue
            restore_objective_hp(cell)
            restored.append((x, y, cell))

    if restored:
        mark_objective_tiles_dirty(map_state)
    return restored


def handle_unit_left_objective_tile(
    map_state: GameMapState,
    from_x: int,
    from_y: int,
) -> bool:
    grid = map_state.objective_tiles
    cell = get_objective_at(grid, from_x, from_y)
    if not cell:
        return False
    if int(cell.get("hp", POKEBALL_MAX_HP)) < int(cell.get("max_hp", POKEBALL_MAX_HP)):
        restore_objective_hp(cell)
        return True
    return False


def format_objective_kind_label(kind: str | None) -> str:
    if str(kind or "").strip().lower() == "master_ball":
        return "master ball"
    return "pokeball"


def apply_capture_damage(
    cell: dict,
    capturer_player_number: int,
    capturer_current_hp: int,
    capturer_max_hp: int,
) -> tuple[bool, bool]:
    """Returns (captured_now, damage_applied)."""
    objective_max_hp = int(cell.get("max_hp", POKEBALL_MAX_HP))
    objective_current_hp = int(cell.get("hp", objective_max_hp))
    unit_current_hp, unit_max_hp = get_capturer_hp_stats(capturer_current_hp, capturer_max_hp)
    damage = compute_capture_damage(unit_current_hp, unit_max_hp)
    new_hp = objective_current_hp - damage
    captured = False
    if new_hp <= 0:
        restore_objective_hp(cell)
        cell["owner"] = capturer_player_number
        captured = True
    else:
        cell["hp"] = new_hp
    return captured, True


def count_owned_pokeballs(grid: list[list[dict | None]] | None, user_id: int, player_order: list[int]) -> int:
    player_number = get_player_number(player_order, int(user_id))
    if player_number is None:
        return 0
    total = 0
    for row in grid or []:
        if not isinstance(row, list):
            continue
        for cell in row:
            if (
                isinstance(cell, dict)
                and cell.get("kind") == "pokeball"
                and int(cell.get("owner") or 0) == player_number
            ):
                total += 1
    return total


def get_war_eliminated_player_ids(
    game: Game,
    state: GameState,
    map_state: GameMapState,
    db: Session,
) -> list[int]:
    if not is_war_game(game) or state.status != "in_progress":
        return []

    player_order = list(state.players or [])
    grid = map_state.objective_tiles
    eliminated: list[int] = []

    for user_id in player_order:
        user_id = int(user_id)
        player_number = get_player_number(player_order, user_id)
        if player_number is None:
            continue

        master_lost = False
        for row in grid or []:
            if not isinstance(row, list):
                continue
            for cell in row:
                if not isinstance(cell, dict) or cell.get("kind") != "master_ball":
                    continue
                original_owner = int(cell.get("original_owner") or cell.get("owner") or 0)
                if original_owner == player_number and int(cell.get("owner") or 0) != player_number:
                    master_lost = True
                    break
            if master_lost:
                break

        unit_count = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game.id,
                GameUnit.user_id == user_id,
                GameUnit.current_hp > 0,
            )
            .count()
        )

        if master_lost or unit_count == 0:
            eliminated.append(user_id)

    return eliminated


def get_war_draw_player_ids(
    game: Game,
    state: GameState,
    db: Session,
    map_state: GameMapState,
) -> list[int]:
    player_order = list(state.players or [])
    grid = map_state.objective_tiles or []

    def pokeball_counts() -> dict[int, int]:
        return {int(pid): count_owned_pokeballs(grid, int(pid), player_order) for pid in player_order}

    def unit_counts() -> dict[int, int]:
        counts: dict[int, int] = {}
        for pid in player_order:
            counts[int(pid)] = (
                db.query(GameUnit)
                .filter(
                    GameUnit.game_id == game.id,
                    GameUnit.user_id == int(pid),
                    GameUnit.current_hp > 0,
                )
                .count()
            )
        return counts

    def cash_counts() -> dict[int, int]:
        counts: dict[int, int] = {}
        for pid in player_order:
            ps = db.query(GamePlayer).filter_by(game_id=game.id, player_id=int(pid)).first()
            counts[int(pid)] = int(ps.cash_remaining or 0) if ps else 0
        return counts

    pb = pokeball_counts()
    max_pb = max(pb.values()) if pb else 0
    candidates = [pid for pid, count in pb.items() if count == max_pb]
    if len(candidates) == 1:
        return candidates

    uc = unit_counts()
    max_units = max(uc.get(pid, 0) for pid in candidates)
    candidates = [pid for pid in candidates if uc.get(pid, 0) == max_units]
    if len(candidates) == 1:
        return candidates

    cash = cash_counts()
    max_cash = max(cash.get(pid, 0) for pid in candidates)
    candidates = [pid for pid in candidates if cash.get(pid, 0) == max_cash]
    return candidates
