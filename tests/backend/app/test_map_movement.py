import pytest

from app.map_movement import (
    IMPOSSIBLE_MOVEMENT_COST,
    LEDGE_DOWN,
    LEDGE_UP,
    build_movement_cost_grid,
    can_enter_tile,
    get_grass_incoming_accuracy_multiplier,
    is_rock_tile,
    is_valid_movement_destination,
    is_water_tile,
    ledge_allows_entry,
    movement_range_with_terrain,
    unit_can_cross_rock,
    unit_can_cross_water,
    unit_can_occupy_tile,
    unit_can_stand_on_ledge,
)


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


def test_unit_can_cross_rock_for_flying_rock_and_levitate():
    assert unit_can_cross_rock({"flying"}) is True
    assert unit_can_cross_rock({"rock"}) is True
    assert unit_can_cross_rock({"grass"}, {"levitate"}) is True
    assert unit_can_cross_rock({"grass"}) is False


def test_build_movement_cost_grid_blocks_water_and_rock():
    base = [[1, 1, 1], [1, 1, 1]]
    special = [[None, "water", "rock"], [None, None, None]]

    blocked = build_movement_cost_grid(base, special, {"grass"})
    assert blocked[0][1] == IMPOSSIBLE_MOVEMENT_COST
    assert blocked[0][2] == IMPOSSIBLE_MOVEMENT_COST

    flying = build_movement_cost_grid(base, special, {"flying"})
    assert flying[0][1] == 1
    assert flying[0][2] == 1

    rock_unit = build_movement_cost_grid(base, special, {"rock"})
    assert rock_unit[0][1] == IMPOSSIBLE_MOVEMENT_COST
    assert rock_unit[0][2] == 1


def test_build_movement_cost_grid_sets_ledge_cost_zero_for_ground_units():
    base = [[2, 2]]
    special = [["ledge_up", "ledge_down"]]

    ground = build_movement_cost_grid(base, special, {"grass"})
    assert ground[0][0] == 0
    assert ground[0][1] == 0

    flying = build_movement_cost_grid(base, special, {"flying"})
    assert flying[0][0] == 2
    assert flying[0][1] == 2

    levitate = build_movement_cost_grid(base, special, {"grass"}, {"levitate"})
    assert levitate[0][0] == 2


def test_grass_tile_incoming_accuracy_multiplier():
    special = [[None, "grass"]]
    assert get_grass_incoming_accuracy_multiplier(special, 1, 0, {"fire"}) == 0.8
    assert get_grass_incoming_accuracy_multiplier(special, 1, 0, {"grass"}) == 1.0
    assert get_grass_incoming_accuracy_multiplier(special, 1, 0, {"bug"}) == 1.0
    assert get_grass_incoming_accuracy_multiplier(special, 0, 0, {"fire"}) == 1.0
    assert get_grass_incoming_accuracy_multiplier(
        special, 1, 0, {"fire"}, {"flying"}
    ) == 1.0
    assert get_grass_incoming_accuracy_multiplier(
        special, 1, 0, {"fire"}, {"grass"}, {"levitate"}
    ) == 1.0


def test_movement_range_skips_impassable_water_tiles():
    costs = [
        [1, IMPOSSIBLE_MOVEMENT_COST, 1],
    ]
    tiles = movement_range_with_terrain(
        start=(0, 0),
        rng=3,
        movement_costs=costs,
        special_tiles=None,
        width=3,
        height=1,
        unit_types={"grass"},
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (1, 0) not in coords
    assert (2, 0) in coords


def test_is_water_tile_reads_special_tiles_grid():
    special = [[None, "water"], ["Water", None]]
    assert is_water_tile(special, 1, 0) is True
    assert is_water_tile(special, 0, 1) is True
    assert is_water_tile(special, 0, 0) is False


def test_is_rock_tile_reads_special_tiles_grid():
    special = [[None, "rock"], [None, None]]
    assert is_rock_tile(special, 1, 0) is True
    assert is_rock_tile(special, 0, 0) is False


def test_ledge_allows_entry_only_from_correct_direction():
    assert ledge_allows_entry(LEDGE_UP, 0, 1, 0, 0) is True
    assert ledge_allows_entry(LEDGE_UP, 0, 0, 0, 1) is False
    assert ledge_allows_entry(LEDGE_DOWN, 0, 0, 0, 1) is True
    assert ledge_allows_entry(LEDGE_DOWN, 0, 1, 0, 0) is False


def test_ledge_pass_through_reaches_tile_beyond_but_not_ledge_itself():
    costs = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
    special = [
        [None, None, None],
        [None, "ledge_up", None],
        [None, None, None],
    ]
    tiles = movement_range_with_terrain(
        start=(1, 2),
        rng=2,
        movement_costs=costs,
        special_tiles=special,
        width=3,
        height=3,
        unit_types={"grass"},
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (1, 1) not in coords
    assert (1, 0) in coords


def test_ledge_cannot_be_entered_from_wrong_direction():
    costs = [[1, 1]]
    special = [[None, "ledge_up"]]
    tiles = movement_range_with_terrain(
        start=(0, 0),
        rng=2,
        movement_costs=costs,
        special_tiles=special,
        width=2,
        height=1,
        unit_types={"grass"},
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (1, 0) not in coords


def test_flying_unit_can_stop_on_ledge():
    costs = [[1, 1]]
    special = [[None, "ledge_up"]]
    tiles = movement_range_with_terrain(
        start=(0, 0),
        rng=1,
        movement_costs=costs,
        special_tiles=special,
        width=2,
        height=1,
        unit_types={"flying"},
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (1, 0) in coords


def test_rock_blocks_non_rock_units():
    costs = [[1, 1]]
    special = [[None, "rock"]]
    effective = build_movement_cost_grid(costs, special, {"grass"})
    tiles = movement_range_with_terrain(
        start=(0, 0),
        rng=2,
        movement_costs=effective,
        special_tiles=special,
        width=2,
        height=1,
        unit_types={"grass"},
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (1, 0) not in coords


def test_unit_can_occupy_tile_for_placement_rules():
    special = [[None, "water"], ["ledge_up", "rock"]]
    assert unit_can_occupy_tile(special, 1, 0, {"water"}) is True
    assert unit_can_occupy_tile(special, 1, 0, {"grass"}) is False
    assert unit_can_occupy_tile(special, 0, 1, {"flying"}) is True
    assert unit_can_occupy_tile(special, 0, 1, {"grass"}) is False
    assert unit_can_occupy_tile(special, 1, 1, {"rock"}) is True
    assert unit_can_occupy_tile(special, 1, 1, {"grass"}) is False


def test_can_enter_tile_and_destination_helpers():
    special = [[None, "ledge_up"]]
    assert can_enter_tile(special, 0, 1, 0, 0, {"grass"}) is True
    assert can_enter_tile(special, 0, 0, 0, 1, {"grass"}) is False
    assert is_valid_movement_destination(special, 0, 0, {"grass"}) is False
    assert is_valid_movement_destination(special, 0, 0, {"flying"}) is True
    assert unit_can_stand_on_ledge({"flying"}) is True
    assert unit_can_stand_on_ledge({"rock"}) is False
