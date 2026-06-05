"""Map tile movement rules (terrain restrictions, water, ledges, rock, etc.)."""

from __future__ import annotations

WATER_TILE = "water"
ROCK_TILE = "rock"
GRASS_TILE = "grass"
GRASS_BASE_DODGE_RATE = 0.10
GRASS_BUG_DODGE_RATE = 0.20
GRASS_BASE_DEFENSE_BOOST = 0.10
GRASS_TYPE_DEFENSE_BOOST = 0.20
LEDGE_UP = "ledge_up"
LEDGE_DOWN = "ledge_down"
LEDGE_LEFT = "ledge_left"
LEDGE_RIGHT = "ledge_right"
LEDGE_TILES = frozenset({LEDGE_UP, LEDGE_DOWN, LEDGE_LEFT, LEDGE_RIGHT})
IMPOSSIBLE_MOVEMENT_COST = 10**9


def normalize_special_tile(cell) -> str | None:
    if cell is None:
        return None
    if isinstance(cell, str):
        value = cell.strip().lower()
        return value or None
    return None


def get_special_tile(special_tiles: list | None, x: int, y: int) -> str | None:
    if not special_tiles or y < 0 or x < 0:
        return None
    if y >= len(special_tiles):
        return None
    row = special_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return None
    return normalize_special_tile(row[x])


def is_water_tile(special_tiles: list | None, x: int, y: int) -> bool:
    return get_special_tile(special_tiles, x, y) == WATER_TILE


def is_rock_tile(special_tiles: list | None, x: int, y: int) -> bool:
    return get_special_tile(special_tiles, x, y) == ROCK_TILE


def is_ledge_tile(special_tiles: list | None, x: int, y: int) -> bool:
    tile = get_special_tile(special_tiles, x, y)
    return tile in LEDGE_TILES if tile else False


def is_grass_tile(special_tiles: list | None, x: int, y: int) -> bool:
    return get_special_tile(special_tiles, x, y) == GRASS_TILE


def target_receives_grass_tile_bonuses(
    target_types: set[str] | None,
    target_ability_names: set[str] | None = None,
) -> bool:
    """Flying and Levitate defenders do not benefit from grass tile cover."""
    if target_types is None:
        return True
    normalized = _normalized_types(target_types)
    if "flying" in normalized:
        return False
    return not unit_has_levitate(target_types, target_ability_names)


def get_grass_dodge_rate(
    special_tiles: list | None,
    target_x: int,
    target_y: int,
    target_types: set[str] | None = None,
    target_ability_names: set[str] | None = None,
) -> float:
    """Return dodge rate (0.0-1.0) for a defender standing on grass."""
    if not is_grass_tile(special_tiles, target_x, target_y):
        return 0.0
    if not target_receives_grass_tile_bonuses(target_types, target_ability_names):
        return 0.0
    if "bug" in _normalized_types(target_types or set()):
        return GRASS_BUG_DODGE_RATE
    return GRASS_BASE_DODGE_RATE


def get_grass_incoming_accuracy_multiplier(
    special_tiles: list | None,
    target_x: int,
    target_y: int,
    target_types: set[str] | None = None,
    target_ability_names: set[str] | None = None,
) -> float:
    """Convert grass-tile dodge rate into an incoming accuracy multiplier."""
    return 1.0 - get_grass_dodge_rate(
        special_tiles, target_x, target_y, target_types, target_ability_names
    )


def get_grass_defense_multiplier(
    special_tiles: list | None,
    target_x: int,
    target_y: int,
    target_types: set[str] | None = None,
    target_ability_names: set[str] | None = None,
) -> float:
    """Grass tiles boost physical and special defense for defenders on the tile."""
    if not is_grass_tile(special_tiles, target_x, target_y):
        return 1.0
    if not target_receives_grass_tile_bonuses(target_types, target_ability_names):
        return 1.0
    if "grass" in _normalized_types(target_types or set()):
        return 1.0 + GRASS_TYPE_DEFENSE_BOOST
    return 1.0 + GRASS_BASE_DEFENSE_BOOST


def _normalized_types(unit_types: set[str]) -> set[str]:
    return {str(t).lower() for t in unit_types}


def _normalized_abilities(ability_names: set[str] | None) -> set[str]:
    if not ability_names:
        return set()
    return {str(a).lower() for a in ability_names}


def unit_has_levitate(
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    return "levitate" in _normalized_abilities(ability_names)


def unit_can_cross_water(
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    normalized_types = _normalized_types(unit_types)
    if normalized_types.intersection({"water", "flying"}):
        return True
    return unit_has_levitate(unit_types, ability_names)


def unit_can_cross_rock(
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    normalized_types = _normalized_types(unit_types)
    if normalized_types.intersection({"flying", "rock"}):
        return True
    return unit_has_levitate(unit_types, ability_names)


def unit_can_stand_on_ledge(
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    """Flying types and Levitate can move onto and stop on ledge tiles."""
    normalized_types = _normalized_types(unit_types)
    if "flying" in normalized_types:
        return True
    return unit_has_levitate(unit_types, ability_names)


def unit_can_pass_through_units(unit_types: set[str]) -> bool:
    """Ghost types can pathfind through allied and enemy units."""
    return "ghost" in _normalized_types(unit_types)


def ledge_allows_entry(
    tile: str,
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
) -> bool:
    """Return True when entering a ledge tile from the required direction."""
    dx = to_x - from_x
    dy = to_y - from_y
    if tile == LEDGE_UP:
        return dy == -1
    if tile == LEDGE_DOWN:
        return dy == 1
    if tile == LEDGE_LEFT:
        return dx == -1
    if tile == LEDGE_RIGHT:
        return dx == 1
    return False


def can_enter_tile(
    special_tiles: list | None,
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    tile = get_special_tile(special_tiles, to_x, to_y)
    if tile is None:
        return True
    if tile in LEDGE_TILES:
        if unit_can_stand_on_ledge(unit_types, ability_names):
            return True
        return ledge_allows_entry(tile, from_x, from_y, to_x, to_y)
    return True


def is_valid_movement_destination(
    special_tiles: list | None,
    x: int,
    y: int,
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    tile = get_special_tile(special_tiles, x, y)
    if tile in LEDGE_TILES and not unit_can_stand_on_ledge(unit_types, ability_names):
        return False
    return True


def build_movement_cost_grid(
    base_costs: list[list[int]],
    special_tiles: list | None,
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> list[list[int]]:
    if not special_tiles:
        return base_costs

    can_water = unit_can_cross_water(unit_types, ability_names)
    can_rock = unit_can_cross_rock(unit_types, ability_names)
    can_stand_on_ledge = unit_can_stand_on_ledge(unit_types, ability_names)

    height = len(base_costs)
    effective: list[list[int]] = []
    for y in range(height):
        row = base_costs[y]
        width = len(row)
        new_row: list[int] = []
        for x in range(width):
            tile = get_special_tile(special_tiles, x, y)
            if tile == WATER_TILE and not can_water:
                new_row.append(IMPOSSIBLE_MOVEMENT_COST)
            elif tile == ROCK_TILE and not can_rock:
                new_row.append(IMPOSSIBLE_MOVEMENT_COST)
            elif tile in LEDGE_TILES and not can_stand_on_ledge:
                new_row.append(0)
            else:
                new_row.append(row[x])
        effective.append(new_row)
    return effective


def movement_range_with_terrain(
    start: tuple[int, int],
    rng: int,
    movement_costs: list[list[int]],
    special_tiles: list | None,
    width: int,
    height: int,
    unit_types: set[str],
    ability_names: set[str] | None = None,
    blocked_tiles: set[tuple[int, int]] | None = None,
) -> list[list[int]]:
    """BFS movement range with water/rock costs and directional ledge pass-through."""
    from collections import deque

    sx, sy = start
    blocked_tiles = blocked_tiles or set()
    seen: set[tuple[int, int]] = set()
    out: list[list[int]] = []
    q = deque([(sx, sy, 0)])
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    while q:
        x, y, c = q.popleft()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        key = (x, y)
        if key in seen:
            continue
        seen.add(key)

        if is_valid_movement_destination(special_tiles, x, y, unit_types, ability_names):
            out.append([x, y])

        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in blocked_tiles:
                continue
            if (nx, ny) in seen:
                continue
            if not can_enter_tile(
                special_tiles, x, y, nx, ny, unit_types, ability_names
            ):
                continue
            step_cost = movement_costs[ny][nx]
            if step_cost >= IMPOSSIBLE_MOVEMENT_COST:
                continue
            nc = c + step_cost
            if nc <= rng:
                q.append((nx, ny, nc))

    return out


def unit_can_occupy_tile(
    special_tiles: list | None,
    x: int,
    y: int,
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    """Whether a unit may be placed on or move onto a tile."""
    tile = get_special_tile(special_tiles, x, y)
    if tile == WATER_TILE:
        return unit_can_cross_water(unit_types, ability_names)
    if tile == ROCK_TILE:
        return unit_can_cross_rock(unit_types, ability_names)
    if tile in LEDGE_TILES:
        return unit_can_stand_on_ledge(unit_types, ability_names)
    return True
