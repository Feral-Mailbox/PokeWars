import pytest

from app.map_movement import (
    IMPOSSIBLE_MOVEMENT_COST,
    build_movement_cost_grid,
    is_water_tile,
    unit_can_cross_water,
)
from app.routes.games import movement_range_backend


def test_unit_can_cross_water_for_water_and_flying_types():
    assert unit_can_cross_water({"water"}) is True
    assert unit_can_cross_water({"flying"}) is True
    assert unit_can_cross_water({"water", "flying"}) is True
    assert unit_can_cross_water({"grass"}) is False
    assert unit_can_cross_water({"fire", "grass"}) is False


def test_unit_can_cross_water_for_levitate_ability():
    assert unit_can_cross_water({"grass"}, {"levitate"}) is True
    assert unit_can_cross_water({"grass"}, {"Levitate"}) is True
    assert unit_can_cross_water({"grass"}, {"intimidate"}) is False


def test_build_movement_cost_grid_blocks_water_for_non_water_units():
    base = [[1, 1], [1, 1]]
    special = [[None, "water"], [None, None]]

    effective = build_movement_cost_grid(base, special, can_cross_water=False)
    assert effective[0][1] == IMPOSSIBLE_MOVEMENT_COST
    assert effective[1][0] == 1

    allowed = build_movement_cost_grid(base, special, can_cross_water=True)
    assert allowed[0][1] == 1


def test_movement_range_backend_skips_impassable_water_tiles():
    costs = [
        [1, IMPOSSIBLE_MOVEMENT_COST, 1],
    ]
    tiles = movement_range_backend(
        start=(0, 0),
        rng=3,
        movement_costs=costs,
        width=3,
        height=1,
        blocked_tiles=set(),
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (1, 0) not in coords
    assert (2, 0) in coords


def test_is_water_tile_reads_special_tiles_grid():
    special = [[None, "water"], ["Water", None]]
    assert is_water_tile(special, 1, 0) is True
    assert is_water_tile(special, 0, 1) is True
    assert is_water_tile(special, 0, 0) is False
