from app.ctf_mode import (
    apply_flag_capture_damage,
    apply_omniboost,
    apply_unlock_damage,
    build_flag_tiles_from_map,
    build_unlock_tiles_from_map,
    capture_damage,
    count_flags_by_owner,
    encode_jail_tile,
    get_jail_at,
    get_jail_tile_for_player,
    get_match_start,
    is_ctf_game,
    is_jail_tile,
    leading_flag_owners,
    list_jail_tiles,
    list_jails,
    make_flag_cell,
    make_jail_cell,
    make_unlock_cell,
    nearest_open_tile,
    parse_jail_tile,
    player_owns_all_flags,
    resolve_jailer_user_id,
    restore_unoccupied_damaged_ctf_tiles,
    total_flag_count,
    unit_blocks_occupation,
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
    def __init__(self, **kwargs):
        self.stat_boosts = {}
        self.flags = {}
        self.user_id = kwargs.get("user_id", 1)
        self.current_hp = kwargs.get("current_hp", 10)
        self.current_x = kwargs.get("current_x", 0)
        self.current_y = kwargs.get("current_y", 0)
        self.starting_x = kwargs.get("starting_x", 0)
        self.starting_y = kwargs.get("starting_y", 0)
        self.match_start_x = kwargs.get("match_start_x")
        self.match_start_y = kwargs.get("match_start_y")
        for key, value in kwargs.items():
            setattr(self, key, value)


class DummyState:
    def __init__(self, players, current_turn=0):
        self.players = players
        self.current_turn = current_turn


def test_is_ctf_game():
    assert is_ctf_game(DummyGame("Capture The Flag")) is True
    assert is_ctf_game(DummyGame("War")) is False


def test_parse_and_list_owned_jails():
    assert parse_jail_tile("ctf_jail_p2") == 2
    assert parse_jail_tile("ctf_jail") is None
    assert is_jail_tile("ctf_jail_p1") is True
    assert encode_jail_tile(3) == "ctf_jail_p3"

    map_obj = DummyMap(
        {
            "flags": [[0, 1, None], [2, None, None], [None, None, None]],
            "special_tiles": [
                ["ctf_jail_p1", None, "ctf_unlock"],
                [None, "grass", "ctf_jail_p2"],
                [None, None, None],
            ],
        }
    )
    flags = build_flag_tiles_from_map(map_obj)
    unlocks = build_unlock_tiles_from_map(map_obj)
    jails = list_jails(map_obj)

    assert flags[0][0] == make_flag_cell(0)
    assert flags[0][1] == make_flag_cell(1)
    assert flags[1][0] == make_flag_cell(2)
    assert flags[0][0]["hp"] == 10
    assert flags[0][0]["max_hp"] == 10
    assert unlocks[0][0] == make_jail_cell(1)
    assert unlocks[1][2] == make_jail_cell(2)
    assert unlocks[0][2] is None
    assert jails == [(0, 0, 1), (2, 1, 2)]
    assert list_jail_tiles(map_obj) == [(0, 0), (2, 1)]
    assert get_jail_tile_for_player(map_obj, 2) == (2, 1)
    assert get_jail_at(map_obj, 0, 0) == {"x": 0, "y": 0, "owner": 1}
    assert get_jail_at(map_obj, 1, 1) is None


def test_capture_damage_and_unlock():
    assert capture_damage(20, 20) == 10
    assert capture_damage(1, 20) == 1
    cell = make_unlock_cell()
    assert apply_unlock_damage(cell, 20, 20) is False
    assert cell["hp"] == 10
    assert apply_unlock_damage(cell, 20, 20) is True
    assert cell["hp"] == 20


def test_flag_capture_damage_uses_hp_ratio():
    cell = make_flag_cell(1)
    assert cell["hp"] == 10
    assert apply_flag_capture_damage(cell, 2, 10, 20) is False
    assert cell["owner"] == 1
    assert cell["hp"] == 5
    assert apply_flag_capture_damage(cell, 2, 20, 20) is True
    assert cell["owner"] == 2
    assert cell["hp"] == 10


def test_restore_unoccupied_damaged_ctf_tiles(monkeypatch):
    monkeypatch.setattr("app.ctf_mode.flag_modified", lambda *_a, **_k: None)

    class DummyMapState:
        def __init__(self):
            flag = make_flag_cell(1)
            flag["hp"] = 4
            jail = make_jail_cell(2)
            jail["hp"] = 8
            self.flag_tiles = [[flag, None], [None, None]]
            self.unlock_tiles = [[None, None], [None, jail]]

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class DummyDb:
        def query(self, _model):
            return Query()

    map_state = DummyMapState()
    restored = restore_unoccupied_damaged_ctf_tiles(map_state, 1, DummyDb())
    kinds = {kind for _x, _y, kind, _cell in restored}
    assert kinds == {"flag", "jail"}
    assert map_state.flag_tiles[0][0]["hp"] == 10
    assert map_state.unlock_tiles[1][1]["hp"] == 20


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


def test_match_start_and_nearest_open_tile():
    unit = DummyUnit(starting_x=4, starting_y=5, match_start_x=1, match_start_y=2)
    assert get_match_start(unit) == (1, 2)
    fallback = DummyUnit(starting_x=7, starting_y=8)
    assert get_match_start(fallback) == (7, 8)
    assert nearest_open_tile((1, 1), {(1, 1)}, 3, 3) != (1, 1)
    assert nearest_open_tile((0, 0), set(), 2, 2) == (0, 0)


def test_jailed_units_do_not_block_occupation():
    free = DummyUnit(current_hp=10, current_x=1, current_y=1)
    jailed = DummyUnit(current_hp=10, current_x=2, current_y=2, flags={"jailed": True})
    assert unit_blocks_occupation(free) is True
    assert unit_blocks_occupation(jailed) is False


def test_resolve_jailer_prefers_last_attacker():
    fainted = DummyUnit(user_id=1, flags={"last_damage_attacker_id": 99})
    attacker = DummyUnit(id=99, user_id=2)

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return attacker

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    assert resolve_jailer_user_id(fainted, FakeDb(), DummyState([1, 2], 0)) == 2


def test_resolve_jailer_falls_back_to_current_turn_player():
    fainted = DummyUnit(user_id=1, flags={})

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    assert resolve_jailer_user_id(fainted, FakeDb(), DummyState([1, 2], 1)) == 2
