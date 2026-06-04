"""Map tile movement rules (terrain restrictions, water, etc.)."""

from __future__ import annotations

WATER_TILE = "water"
IMPOSSIBLE_MOVEMENT_COST = 10**9


def normalize_special_tile(cell) -> str | None:
    if cell is None:
        return None
    if isinstance(cell, str):
        value = cell.strip().lower()
        return value or None
    return None


def is_water_tile(special_tiles: list | None, x: int, y: int) -> bool:
    if not special_tiles or y < 0 or x < 0:
        return False
    if y >= len(special_tiles):
        return False
    row = special_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return False
    return normalize_special_tile(row[x]) == WATER_TILE


def unit_can_cross_water(
    unit_types: set[str],
    ability_names: set[str] | None = None,
) -> bool:
    normalized_types = {str(t).lower() for t in unit_types}
    if normalized_types.intersection({"water", "flying"}):
        return True
    if ability_names and "levitate" in {str(a).lower() for a in ability_names}:
        return True
    return False


def build_movement_cost_grid(
    base_costs: list[list[int]],
    special_tiles: list | None,
    can_cross_water: bool,
) -> list[list[int]]:
    if can_cross_water or not special_tiles:
        return base_costs

    height = len(base_costs)
    effective: list[list[int]] = []
    for y in range(height):
        row = base_costs[y]
        width = len(row)
        new_row: list[int] = []
        for x in range(width):
            if is_water_tile(special_tiles, x, y):
                new_row.append(IMPOSSIBLE_MOVEMENT_COST)
            else:
                new_row.append(row[x])
        effective.append(new_row)
    return effective
