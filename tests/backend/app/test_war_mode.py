import pytest

from app.war_mode import (
    apply_capture_damage,
    build_objective_tiles_from_map,
    calculate_war_income,
    can_capture_objective,
    can_summon_on_objective,
    compute_capture_damage,
    count_owned_objectives,
    format_objective_kind_label,
    get_current_round,
    get_war_draw_player_ids,
    make_objective_cell,
    parse_objective_from_special_tile,
)


class DummyMap:
    def __init__(self, tile_data, height=3, width=3):
        self.tile_data = tile_data
        self.height = height
        self.width = width


class DummyGame:
    def __init__(self, cash_per_turn=100):
        self.cash_per_turn = cash_per_turn
        self.id = 1


class DummyState:
    def __init__(self, players, current_turn=0):
        self.players = players
        self.current_turn = current_turn
        self.status = "in_progress"


class DummyMapState:
    def __init__(self, grid):
        self.objective_tiles = grid


def test_parse_objective_from_special_tile():
    assert parse_objective_from_special_tile("pokeball") == ("pokeball", 0)
    assert parse_objective_from_special_tile("master_ball_p2") == ("master_ball", 2)
    assert parse_objective_from_special_tile("pokeball_p3") == ("pokeball", 3)
    assert parse_objective_from_special_tile("grass") is None


def test_compute_capture_damage():
    assert compute_capture_damage(20, 20) == 10
    assert compute_capture_damage(1, 20) == 1
    assert compute_capture_damage(15, 20) == 8


def test_format_objective_kind_label():
    assert format_objective_kind_label("pokeball") == "pokeball"
    assert format_objective_kind_label("master_ball") == "master ball"


def test_apply_capture_damage_reduces_hp_before_capture():
    cell = make_objective_cell("pokeball", 2)
    captured, _ = apply_capture_damage(cell, 1, capturer_current_hp=20, capturer_max_hp=20)
    assert captured is False
    assert cell["hp"] == 10
    assert cell["owner"] == 2


def test_apply_capture_damage_uses_capturer_hp_not_objective_hp():
    cell = make_objective_cell("pokeball", 2)
    cell["hp"] = 8
    # Wounded objective would deal 8 damage if formula used pokeball HP; unit at half HP deals 5.
    captured, _ = apply_capture_damage(cell, 1, capturer_current_hp=10, capturer_max_hp=20)
    assert captured is False
    assert cell["hp"] == 3
    assert cell["owner"] == 2


def test_handle_unit_left_objective_tile_restores_hp():
    from app.war_mode import handle_unit_left_objective_tile

    cell = make_objective_cell("pokeball", 0)
    cell["hp"] = 10
    grid = [[cell]]
    map_state = DummyMapState(grid)
    assert handle_unit_left_objective_tile(map_state, 0, 0) is True
    assert cell["hp"] == 20


def test_restore_unoccupied_damaged_objectives():
    from app.war_mode import restore_unoccupied_damaged_objectives

    cell = make_objective_cell("pokeball", 0)
    cell["hp"] = 10
    grid = [[cell]]
    map_state = DummyMapState(grid)

    class DummyUnit:
        def __init__(self, x, y):
            self.current_x = x
            self.current_y = y
            self.is_fainted = False
            self.current_hp = 100

    class DummyQuery:
        def __init__(self, units):
            self.units = units

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return self.units

    class DummySession:
        def __init__(self, units):
            self.units = units

        def query(self, model):
            return DummyQuery(self.units)

    db = DummySession([DummyUnit(0, 0)])
    assert restore_unoccupied_damaged_objectives(map_state, 1, db) == []

    db = DummySession([])
    restored = restore_unoccupied_damaged_objectives(map_state, 1, db)
    assert len(restored) == 1
    assert cell["hp"] == 20


def test_apply_capture_damage_transfers_ownership():
    cell = make_objective_cell("pokeball", 0)
    cell["hp"] = 10
    captured, _ = apply_capture_damage(cell, 2, capturer_current_hp=150, capturer_max_hp=150)
    assert captured is True
    assert cell["owner"] == 2
    assert cell["hp"] == 20


def test_build_objective_tiles_from_map_and_income():
    tile_data = {
        "special_tiles": [
            ["master_ball_p1", "pokeball", None],
            [None, "pokeball_p2", None],
            [None, None, "master_ball_p2"],
        ],
        "spawn_points": [[1, 1, None], [None, None, 2], [None, None, 2]],
    }
    map_obj = DummyMap(tile_data, height=3, width=3)
    grid = build_objective_tiles_from_map(map_obj, [10, 20])
    assert grid[0][0]["kind"] == "master_ball"
    assert grid[0][1]["owner"] == 0
    assert grid[1][1]["owner"] == 2
    assert count_owned_objectives(grid, 1) == 1
    assert count_owned_objectives(grid, 2) == 2
    assert calculate_war_income(DummyGame(100), grid, 2) == 200


def test_can_summon_and_capture_rules():
    cell = make_objective_cell("pokeball", 1, last_summon_round=2)
    assert can_summon_on_objective(cell, 1, 2) is False
    assert can_summon_on_objective(cell, 1, 3) is True
    assert can_capture_objective(cell, 2) is True
    assert can_capture_objective(cell, 1) is False


def test_get_current_round():
    state = DummyState([1, 2, 3], current_turn=3)
    assert get_current_round(state) == 2
