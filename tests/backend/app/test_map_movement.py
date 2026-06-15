import pytest

from app.map_movement import (
    IMPOSSIBLE_MOVEMENT_COST,
    LEDGE_DOWN,
    LEDGE_UP,
    SAND_MOVEMENT_COST,
    STUMP_MOVEMENT_COST,
    build_movement_cost_grid,
    can_enter_tile,
    find_shortest_path,
    get_grass_defense_multiplier,
    get_stump_defense_multiplier,
    get_tile_defense_multiplier,
    get_grass_incoming_accuracy_multiplier,
    is_ice_tile,
    is_rock_tile,
    is_sand_tile,
    is_valid_movement_destination,
    is_water_tile,
    ledge_allows_entry,
    movement_range_with_terrain,
    resolve_movement_destination,
    slide_on_ice_from,
    unit_can_cross_rock,
    unit_can_cross_water,
    unit_can_occupy_tile,
    unit_can_pass_through_units,
    unit_can_stand_on_ledge,
    unit_ignores_ice_slide,
    unit_ignores_sand_slow,
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


def test_unit_ignores_sand_slow_for_ground_flying_and_levitate():
    assert unit_ignores_sand_slow({"ground"}) is True
    assert unit_ignores_sand_slow({"flying"}) is True
    assert unit_ignores_sand_slow({"ground", "flying"}) is True
    assert unit_ignores_sand_slow({"grass"}, {"levitate"}) is True
    assert unit_ignores_sand_slow({"grass"}, {"Levitate"}) is True
    assert unit_ignores_sand_slow({"grass"}) is False
    assert unit_ignores_sand_slow({"fire", "water"}) is False


def test_build_movement_cost_grid_sets_sand_cost_for_non_exempt_units():
    base = [[1, 1, 1]]
    special = [[None, "sand", None]]

    slow = build_movement_cost_grid(base, special, {"grass"})
    assert slow[0][1] == SAND_MOVEMENT_COST
    assert slow[0][0] == 1
    assert slow[0][2] == 1

    ground = build_movement_cost_grid(base, special, {"ground"})
    assert ground[0][1] == 1

    flying = build_movement_cost_grid(base, special, {"flying"})
    assert flying[0][1] == 1

    levitate = build_movement_cost_grid(base, special, {"grass"}, {"levitate"})
    assert levitate[0][1] == 1


def test_sand_reduces_movement_range_for_non_exempt_units():
    base = [[1, 1, 1]]
    special = [[None, "sand", None]]
    effective = build_movement_cost_grid(base, special, {"grass"})

    tiles = movement_range_with_terrain(
        start=(0, 0),
        rng=2,
        movement_costs=effective,
        special_tiles=special,
        width=3,
        height=1,
        unit_types={"grass"},
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (1, 0) in coords
    assert (2, 0) not in coords

    ground_tiles = movement_range_with_terrain(
        start=(0, 0),
        rng=2,
        movement_costs=build_movement_cost_grid(base, special, {"ground"}),
        special_tiles=special,
        width=3,
        height=1,
        unit_types={"ground"},
    )
    ground_coords = {(t[0], t[1]) for t in ground_tiles}
    assert (1, 0) in ground_coords
    assert (2, 0) in ground_coords


def test_unit_ignores_ice_slide_for_ice_flying_and_levitate():
    assert unit_ignores_ice_slide({"ice"}) is True
    assert unit_ignores_ice_slide({"flying"}) is True
    assert unit_ignores_ice_slide({"ice", "flying"}) is True
    assert unit_ignores_ice_slide({"grass"}, {"levitate"}) is True
    assert unit_ignores_ice_slide({"grass"}, {"Levitate"}) is True
    assert unit_ignores_ice_slide({"grass"}) is False
    assert unit_ignores_ice_slide({"fire", "water"}) is False


def test_slide_on_ice_from_stops_on_first_non_ice_tile():
    special = [[None, "ice", "ice", None]]
    costs = [[1, 1, 1, 1]]
    assert slide_on_ice_from(1, 0, 1, 0, special, 4, 1, {"grass"}) == (3, 0)


def test_slide_on_ice_from_stops_before_occupied_tile():
    special = [[None, "ice", None, None]]
    costs = [[1, 1, 1, 1]]
    occupied = {(2, 0)}
    assert slide_on_ice_from(1, 0, 1, 0, special, 4, 1, {"grass"}, occupied=occupied) == (1, 0)


def test_resolve_movement_destination_slides_when_entering_ice():
    special = [[None, "ice", "ice", None]]
    costs = [[1, 1, 1, 1]]

    final_x, final_y, slid = resolve_movement_destination(
        0, 0, 1, 0, costs, special, 4, 1, {"grass"}
    )
    assert slid is True
    assert (final_x, final_y) == (3, 0)

    ice_unit_x, ice_unit_y, ice_slid = resolve_movement_destination(
        0, 0, 1, 0, costs, special, 4, 1, {"ice"}
    )
    assert ice_slid is False
    assert (ice_unit_x, ice_unit_y) == (1, 0)

    flying_x, flying_y, flying_slid = resolve_movement_destination(
        0, 0, 2, 0, costs, special, 4, 1, {"flying"}
    )
    assert flying_slid is False
    assert (flying_x, flying_y) == (2, 0)


def test_resolve_movement_destination_does_not_retrigger_slide_from_ice_to_ice():
    special = [["ice", "ice", None]]
    costs = [[1, 1, 1]]

    final_x, final_y, slid = resolve_movement_destination(
        0, 0, 2, 0, costs, special, 3, 1, {"grass"}
    )
    assert slid is False
    assert (final_x, final_y) == (2, 0)


def test_find_shortest_path_reaches_destination():
    costs = [[1, 1, 1]]
    path = find_shortest_path((0, 0), (2, 0), costs, None, 3, 1, {"grass"})
    assert path == [(0, 0), (1, 0), (2, 0)]


def test_is_ice_tile_reads_special_tiles_grid():
    special = [[None, "ice"], ["Ice", None]]
    assert is_ice_tile(special, 1, 0) is True
    assert is_ice_tile(special, 0, 1) is True
    assert is_ice_tile(special, 0, 0) is False


def test_is_sand_tile_reads_special_tiles_grid():
    special = [[None, "sand"], ["Sand", None]]
    assert is_sand_tile(special, 1, 0) is True
    assert is_sand_tile(special, 0, 1) is True
    assert is_sand_tile(special, 0, 0) is False


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


def test_unit_can_pass_through_units_for_ghost_type():
    assert unit_can_pass_through_units({"ghost"}) is True
    assert unit_can_pass_through_units({"ghost", "poison"}) is True
    assert unit_can_pass_through_units({"grass"}) is False


def test_ghost_units_pathfind_through_blocked_unit_tiles():
    costs = [[1, 1, 1]]
    tiles = movement_range_with_terrain(
        start=(0, 0),
        rng=3,
        movement_costs=costs,
        special_tiles=None,
        width=3,
        height=1,
        unit_types={"ghost"},
        blocked_tiles={(1, 0)},
    )
    coords = {(t[0], t[1]) for t in tiles}
    assert (2, 0) in coords

    blocked = movement_range_with_terrain(
        start=(0, 0),
        rng=3,
        movement_costs=costs,
        special_tiles=None,
        width=3,
        height=1,
        unit_types={"normal"},
        blocked_tiles={(1, 0)},
    )
    blocked_coords = {(t[0], t[1]) for t in blocked}
    assert (2, 0) not in blocked_coords


def test_grass_tile_incoming_accuracy_multiplier():
    special = [[None, "grass"]]
    assert get_grass_incoming_accuracy_multiplier(special, 1, 0, {"fire"}) == pytest.approx(0.9)
    assert get_grass_incoming_accuracy_multiplier(special, 1, 0, {"grass"}) == pytest.approx(0.9)
    assert get_grass_incoming_accuracy_multiplier(special, 1, 0, {"bug"}) == pytest.approx(0.8)
    assert get_grass_incoming_accuracy_multiplier(special, 0, 0, {"fire"}) == 1.0
    assert get_grass_incoming_accuracy_multiplier(
        special, 1, 0, {"flying"}
    ) == 1.0
    assert get_grass_incoming_accuracy_multiplier(
        special, 1, 0, {"grass"}, {"levitate"}
    ) == 1.0


def test_grass_tile_defense_multiplier():
    special = [[None, "grass"]]
    assert get_grass_defense_multiplier(special, 1, 0, {"fire"}) == pytest.approx(1.1)
    assert get_grass_defense_multiplier(special, 1, 0, {"grass"}) == pytest.approx(1.2)
    assert get_grass_defense_multiplier(special, 1, 0, {"bug"}) == pytest.approx(1.1)
    assert get_grass_defense_multiplier(special, 1, 0, {"grass", "bug"}) == pytest.approx(1.2)
    assert get_grass_defense_multiplier(special, 0, 0, {"fire"}) == 1.0
    assert get_grass_defense_multiplier(special, 1, 0, {"flying"}) == 1.0
    assert get_grass_defense_multiplier(
        special, 1, 0, {"grass"}, {"levitate"}
    ) == 1.0


def test_stump_tile_movement_and_defense():
    special = [["stump"]]
    costs = build_movement_cost_grid([[1]], special, {"flying"})
    assert costs[0][0] == STUMP_MOVEMENT_COST

    assert get_stump_defense_multiplier(special, 0, 0, {"fire"}) == pytest.approx(1.2)
    assert get_stump_defense_multiplier(special, 0, 0, {"grass"}) == pytest.approx(1.2)
    assert get_stump_defense_multiplier(special, 0, 0, {"flying"}) == 1.0
    assert get_stump_defense_multiplier(special, 0, 0, {"fire"}, {"levitate"}) == 1.0

    combined = get_tile_defense_multiplier(special, 0, 0, {"grass"})
    assert combined == pytest.approx(1.2)


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


def test_impassable_tile_blocks_all_units():
    special = [["impassable"]]
    for types in ({"grass"}, {"flying"}, {"water"}, {"ghost"}):
        assert unit_can_occupy_tile(special, 0, 0, types) is False
        assert unit_can_occupy_tile(special, 0, 0, types, {"levitate"}) is False

    costs = build_movement_cost_grid([[1]], special, {"flying"})
    assert costs[0][0] == IMPOSSIBLE_MOVEMENT_COST

    assert can_enter_tile(special, 0, 0, 0, 0, {"flying"}) is False
    assert is_valid_movement_destination(special, 0, 0, {"flying"}) is False


def test_can_enter_tile_and_destination_helpers():
    special = [[None, "ledge_up"]]
    assert can_enter_tile(special, 0, 1, 0, 0, {"grass"}) is True
    assert can_enter_tile(special, 0, 0, 0, 1, {"grass"}) is False
    assert is_valid_movement_destination(special, 0, 0, {"grass"}) is False
    assert is_valid_movement_destination(special, 0, 0, {"flying"}) is True
    assert unit_can_stand_on_ledge({"flying"}) is True
    assert unit_can_stand_on_ledge({"rock"}) is False
