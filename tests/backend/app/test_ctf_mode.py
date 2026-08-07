from app.ctf_mode import (
    apply_omniboost,
    apply_unlock_damage,
    build_flag_tiles_from_map,
    build_unlock_tiles_from_map,
    capture_damage,
    count_flags_by_owner,
    is_ctf_game,
    leading_flag_owners,
    list_jail_tiles,
    make_flag_cell,
    make_unlock_cell,
    player_owns_all_flags,
    total_flag_count,
)


class DummyMap:
    def __init__(self, tile_data, height=3, width=3):
        self.tile_data = tile_data
        self.height = height
        self.width = width


class DummyGame:
    def __init__(self, gamemode="Capture The Flag"):
        self.gamemode = gamemode


class DummyUnit:
    def __init__(self):
        self.stat_boosts = {}
        self.flags = {}


def test_is_ctf_game():
    assert is_ctf_game(DummyGame("Capture The Flag")) is True
    assert is_ctf_game(DummyGame("War")) is False


def test_build_flag_and_unlock_tiles_from_map():
    map_obj = DummyMap(
        {
            "flags": [[0, 1, None], [2, None, None], [None, None, None]],
            "special_tiles": [
                ["ctf_jail", None, "ctf_unlock"],
                [None, "grass", None],
                [None, None, None],
            ],
        }
    )
    flags = build_flag_tiles_from_map(map_obj)
    unlocks = build_unlock_tiles_from_map(map_obj)
    jails = list_jail_tiles(map_obj)

    assert flags[0][0] == make_flag_cell(0)
    assert flags[0][1] == make_flag_cell(1)
    assert flags[1][0] == make_flag_cell(2)
    assert flags[0][2] is None
    assert unlocks[0][2] == make_unlock_cell()
    assert unlocks[0][0] is None
    assert jails == [(0, 0)]


def test_capture_damage_and_unlock():
    assert capture_damage(20, 20) == 10
    assert capture_damage(1, 20) == 1
    cell = make_unlock_cell()
    assert apply_unlock_damage(cell, 20, 20) is False
    assert cell["hp"] == 10
    assert apply_unlock_damage(cell, 20, 20) is True
    assert cell["hp"] == 20


def test_flag_ownership_helpers():
    grid = [
        [make_flag_cell(1), make_flag_cell(1)],
        [make_flag_cell(2), None],
    ]
    assert total_flag_count(grid) == 3
    assert count_flags_by_owner(grid) == {1: 2, 2: 1}
    assert player_owns_all_flags(grid, 1) is False

    all_owned = [
        [make_flag_cell(1), make_flag_cell(1)],
        [make_flag_cell(1), None],
    ]
    assert player_owns_all_flags(all_owned, 1) is True
    assert leading_flag_owners(grid, [10, 20]) == [10]


def test_apply_omniboost_sets_three_turn_stages(monkeypatch):
    unit = DummyUnit()

    class FakeDb:
        def add(self, _obj):
            return None

    monkeypatch.setattr("app.ctf_mode.flag_modified", lambda *_args, **_kwargs: None)
    apply_omniboost(unit, FakeDb())
    for stat in ("attack", "defense", "sp_attack", "sp_defense", "speed"):
        assert unit.stat_boosts[stat] == [{"magnitude": 1, "expires_turn": 3}]
    assert "hp" not in unit.stat_boosts
