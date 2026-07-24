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


def test_restore_unoccupied_damaged_objectives(monkeypatch):
    from app.war_mode import restore_unoccupied_damaged_objectives

    monkeypatch.setattr("app.war_mode.mark_objective_tiles_dirty", lambda _state: None)

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


def test_get_current_round_defaults_when_no_players_or_turn():
    assert get_current_round(DummyState([], current_turn=0)) == 1
    state = DummyState([1, 2], current_turn=None)
    assert get_current_round(state) == 1


def test_parse_blank_and_is_objective_special_tile():
    from app.war_mode import is_objective_special_tile

    assert parse_objective_from_special_tile("   ") is None
    assert is_objective_special_tile("pokeball") is True
    assert is_objective_special_tile("grass") is False
    assert is_objective_special_tile(None) is False


def test_find_spawn_center_and_auto_master_ball():
    from app.war_mode import _find_spawn_center

    assert _find_spawn_center(None, 1) is None
    assert _find_spawn_center([[1, 1], [1, None]], 1) == (0, 0)

    # Map without master_ball tiles — auto-place from spawn centers.
    # Non-list special row is skipped; player 2 gets an auto master_ball.
    tile_data = {
        "special_tiles": [["pokeball", None], "bad-row"],
        "spawn_points": [
            [1, 1],
            [2, 2],
        ],
    }
    map_obj = DummyMap(tile_data, height=2, width=2)
    grid = build_objective_tiles_from_map(map_obj, [10, 20])
    assert grid[0][0]["kind"] == "pokeball"
    assert any(
        cell and cell.get("kind") == "master_ball" and cell.get("owner") == 2
        for row in grid
        for cell in row
    )


def test_build_merges_existing_objective_state():
    tile_data = {
        "special_tiles": [["pokeball", None], [None, None]],
        "spawn_points": [[1, None], [None, 2]],
    }
    map_obj = DummyMap(tile_data, height=2, width=2)
    existing = [
        [{"kind": "pokeball", "owner": 2, "hp": 7, "last_summon_round": 4}, None],
        [None, None],
    ]
    grid = build_objective_tiles_from_map(map_obj, [10, 20], existing=existing)
    assert grid[0][0]["owner"] == 2
    assert grid[0][0]["hp"] == 7
    assert grid[0][0]["last_summon_round"] == 4


def test_get_objective_at_bounds():
    from app.war_mode import get_objective_at

    assert get_objective_at(None, 0, 0) is None
    assert get_objective_at([[{"kind": "pokeball"}]], -1, 0) is None
    assert get_objective_at([[{"kind": "pokeball"}]], 0, 5) is None
    assert get_objective_at([["bad"]], 0, 0) is None
    assert get_objective_at([[{"kind": "pokeball"}]], 0, 0)["kind"] == "pokeball"


def test_count_owned_objectives_edge_cases():
    assert count_owned_objectives(None, 1) == 0
    assert count_owned_objectives([[make_objective_cell("pokeball", 1)]], 0) == 0
    assert count_owned_objectives(["bad-row", [make_objective_cell("pokeball", 1)]], 1) == 1


def test_apply_war_round_income_adds_cash_and_early_exits(monkeypatch):
    from app.war_mode import apply_war_round_income

    class PlayerState:
        def __init__(self):
            self.cash_remaining = 50

    class DummyQuery:
        def __init__(self, player):
            self.player = player

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return self.player

    class DummySession:
        def __init__(self, player):
            self.player = player

        def query(self, model):
            return DummyQuery(self.player)

    game = DummyGame(100)
    game.gamemode = "War"
    state = DummyState([10])
    grid = [[make_objective_cell("pokeball", 1)]]
    map_state = DummyMapState(grid)
    player = PlayerState()
    apply_war_round_income(game, state, map_state, DummySession(player))
    assert player.cash_remaining == 150

    # Early exits
    game.gamemode = "Conquest"
    apply_war_round_income(game, state, map_state, DummySession(player))
    game.gamemode = "War"
    apply_war_round_income(game, state, DummyMapState([]), DummySession(player))
    game.cash_per_turn = 0
    apply_war_round_income(game, state, map_state, DummySession(player))


def test_capture_damage_and_hp_stats_zero_max():
    from app.war_mode import get_capturer_hp_stats

    assert compute_capture_damage(10, 0) == 1
    assert get_capturer_hp_stats(5, 0) == (5, 5)
    assert get_capturer_hp_stats(0, 0) == (0, 1)


def test_player_owns_master_ball_and_original_owner():
    from app.war_mode import (
        get_master_ball_original_owner,
        mark_master_ball_original_owners,
        player_owns_master_ball,
    )

    assert player_owns_master_ball(None, 1) is False
    assert player_owns_master_ball(["bad", [make_objective_cell("master_ball", 1)]], 1) is True
    assert player_owns_master_ball([[make_objective_cell("pokeball", 1)]], 1) is False

    cell = make_objective_cell("master_ball", 2)
    assert get_master_ball_original_owner(cell) == 2
    assert get_master_ball_original_owner(make_objective_cell("pokeball", 1)) is None
    orphan = {"kind": "master_ball", "owner": 3}
    assert get_master_ball_original_owner(orphan) == 3

    grid = [["bad", {"kind": "master_ball", "owner": 1}]]
    mark_master_ball_original_owners(None)
    mark_master_ball_original_owners(grid)
    assert grid[0][1]["original_owner"] == 1


def test_can_summon_rejects_non_owner():
    cell = make_objective_cell("pokeball", 1)
    assert can_summon_on_objective(cell, 2, 1) is False


def test_handle_unit_left_no_cell_or_full_hp():
    from app.war_mode import handle_unit_left_objective_tile

    map_state = DummyMapState([[None]])
    assert handle_unit_left_objective_tile(map_state, 0, 0) is False
    cell = make_objective_cell("pokeball", 1)
    map_state = DummyMapState([[cell]])
    assert handle_unit_left_objective_tile(map_state, 0, 0) is False


def test_restore_unoccupied_empty_grid_and_bad_rows(monkeypatch):
    from app.war_mode import restore_unoccupied_damaged_objectives

    monkeypatch.setattr("app.war_mode.mark_objective_tiles_dirty", lambda _state: None)

    class DummyQuery:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class DummySession:
        def query(self, model):
            return DummyQuery()

    assert restore_unoccupied_damaged_objectives(DummyMapState([]), 1, DummySession()) == []
    cell = make_objective_cell("pokeball", 0)
    cell["hp"] = 5
    map_state = DummyMapState(["bad-row", [cell]])
    restored = restore_unoccupied_damaged_objectives(map_state, 1, DummySession())
    assert len(restored) == 1


def test_count_owned_pokeballs_unknown_player():
    from app.war_mode import count_owned_pokeballs

    grid = [["bad", make_objective_cell("pokeball", 1)]]
    assert count_owned_pokeballs(grid, 999, [10, 20]) == 0
    assert count_owned_pokeballs(grid, 10, [10, 20]) == 1


def test_get_war_eliminated_not_in_progress_and_conditions():
    from app.war_mode import get_war_eliminated_player_ids

    class DummyQuery:
        def __init__(self, count_value):
            self.count_value = count_value

        def filter(self, *args, **kwargs):
            return self

        def count(self):
            return self.count_value

    class DummySession:
        def __init__(self, count_value):
            self.count_value = count_value

        def query(self, model):
            return DummyQuery(self.count_value)

    game = DummyGame()
    game.gamemode = "Conquest"
    state = DummyState([10, 20])
    map_state = DummyMapState([[]])
    assert get_war_eliminated_player_ids(game, state, map_state, DummySession(1)) == []

    game.gamemode = "War"
    state.status = "finished"
    assert get_war_eliminated_player_ids(game, state, map_state, DummySession(1)) == []

    state.status = "in_progress"
    stolen = make_objective_cell("master_ball", 1)
    stolen["original_owner"] = 1
    stolen["owner"] = 2
    map_state = DummyMapState(["bad", [stolen]])
    # Player 1 lost master ball; player 2 has zero units.
    eliminated = get_war_eliminated_player_ids(game, state, map_state, DummySession(0))
    assert 10 in eliminated
    assert 20 in eliminated


def test_get_war_draw_tiebreak_units_then_cash():
    from app.war_mode import get_war_draw_player_ids

    class DummyQuery:
        def __init__(self, *, count_value=0, player=None):
            self.count_value = count_value
            self.player = player

        def filter(self, *args, **kwargs):
            return self

        def filter_by(self, **kwargs):
            return self

        def count(self):
            return self.count_value

        def first(self):
            return self.player

    class DummySession:
        def __init__(self, unit_counts, cash_by_pid):
            self.unit_counts = unit_counts
            self.cash_by_pid = cash_by_pid
            self._last_user = None

        def query(self, model):
            # Track which lookup path based on model name
            name = getattr(model, "__name__", str(model))
            if name == "GameUnit":
                # Return a query that uses count from unit_counts after filter
                session = self

                class UnitQuery(DummyQuery):
                    def filter(self, *args, **kwargs):
                        return self

                    def count(self):
                        # Called once per player in order; pop from sequence
                        if not hasattr(session, "_unit_iter"):
                            session._unit_iter = iter(
                                session.unit_counts[pid] for pid in [10, 20, 30]
                            )
                        return next(session._unit_iter)

                return UnitQuery()

            session = self

            class PlayerQuery(DummyQuery):
                def filter_by(self, **kwargs):
                    pid = kwargs.get("player_id")
                    cash = session.cash_by_pid.get(pid, 0)
                    self.player = type("P", (), {"cash_remaining": cash})()
                    return self

            return PlayerQuery()

    game = DummyGame()
    game.gamemode = "War"
    state = DummyState([10, 20, 30])
    # Equal pokeballs for all → tiebreak on units → then cash
    grid = [
        [
            make_objective_cell("pokeball", 1),
            make_objective_cell("pokeball", 2),
            make_objective_cell("pokeball", 3),
        ]
    ]
    map_state = DummyMapState(grid)

    # Units: 10 and 20 tied high, 30 lower → then cash decides between 10 and 20
    db = DummySession(unit_counts={10: 5, 20: 5, 30: 1}, cash_by_pid={10: 100, 20: 200, 30: 50})
    winners = get_war_draw_player_ids(game, state, db, map_state)
    assert winners == [20]

    # Single pokeball leader
    grid2 = [[make_objective_cell("pokeball", 1), make_objective_cell("pokeball", 1)]]
    winners2 = get_war_draw_player_ids(
        game,
        state,
        DummySession(unit_counts={10: 1, 20: 9, 30: 9}, cash_by_pid={10: 0, 20: 0, 30: 0}),
        DummyMapState(grid2),
    )
    assert winners2 == [10]
