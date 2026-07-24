import app.db.models as models
from app.routes.games import (
    get_field_effect_at_position,
    get_move_hit_count,
    get_scaling_hit_powers,
    get_timed_effect_id_at_position,
    get_unit_coords,
    get_unit_flags,
    get_unit_held_item,
    get_weather_id_at_position,
    is_gravity_active_at,
    move_has_effect_token,
    move_has_revive_effect,
    move_ignores_fairy_immunity,
    move_ignores_redirect,
    move_requires_attacker_berry,
    move_requires_target_held_item,
    move_uses_best_offense,
    move_uses_separate_hit_accuracy,
    normalize_timed_tile_cell,
    preparation_item_allowed,
    set_unit_flags,
    set_unit_held_item,
    terrain_condition_matches,
    unit_has_glaive_rush,
    unit_has_positive_stat_stage,
    unit_has_status_condition,
    weather_condition_matches,
    WEATHER_TO_ID,
)


def test_get_unit_coords_preserves_origin():
    unit = models.GameUnit(current_x=0, current_y=0)
    assert get_unit_coords(unit) == (0, 0)


def test_get_unit_coords_defaults_when_missing():
    unit = models.GameUnit()
    unit.current_x = None
    unit.current_y = None
    assert get_unit_coords(unit) == (-1, -1)


def test_normalize_timed_tile_cell_variants():
    assert normalize_timed_tile_cell([2, 5]) == [2, 5]
    assert normalize_timed_tile_cell([3])[0] == 3
    assert normalize_timed_tile_cell(4)[0] == 4
    assert normalize_timed_tile_cell(None) == [0, 0]
    assert normalize_timed_tile_cell("bad") == [0, 0]


def test_timed_and_weather_lookups():
    tiles = [[[1, 3], [0, 0]], [[2, 2], [0, 0]]]
    assert get_timed_effect_id_at_position(tiles, 0, 0) == 1
    assert get_timed_effect_id_at_position(tiles, -1, 0) == 0
    weather = [[1, 0], [0, 2]]
    assert get_weather_id_at_position(weather, 0, 0) == 1
    assert get_weather_id_at_position(weather, 1, 1) == 2


def test_terrain_and_weather_condition_matches():
    assert terrain_condition_matches(1, "electric") is True
    assert terrain_condition_matches(0, "none") is True
    assert terrain_condition_matches(2, "*") is True
    assert weather_condition_matches(0, "clear") is True
    assert weather_condition_matches(WEATHER_TO_ID["sun"], "sun") is True
    assert weather_condition_matches(2, "*") is True
    assert weather_condition_matches(1, "rain") is False


def test_field_effect_and_gravity():
    field = [[0, 1], [0, 0]]
    unit = models.GameUnit(current_x=1, current_y=0)
    assert get_field_effect_at_position(field, 1, 0) == 1
    assert is_gravity_active_at(unit, field) is True
    assert is_gravity_active_at(models.GameUnit(current_x=0, current_y=0), field) is False


def test_move_effect_helpers():
    move = models.Move(
        name="Test",
        type="Normal",
        category="Physical",
        effects=[
            "target:revive",
            "self:ignore_fairy_immunity",
            "ignore_redirect",
            "self:use_best_offense",
            "requires:target:held_item",
            "requires:held_item:berry",
            "multi_hit:scaling:10,20:separate_accuracy",
        ],
    )
    assert move_has_effect_token(move, "ignore_redirect") is True
    assert move_has_revive_effect(move) is True
    assert move_ignores_fairy_immunity(move) is True
    assert move_ignores_redirect(move) is True
    assert move_uses_best_offense(move) is True
    assert move_requires_target_held_item(move) is True
    assert move_requires_attacker_berry(move) is True
    assert move_uses_separate_hit_accuracy(move) is True


def test_hit_count_and_scaling_powers():
    move = models.Move(
        name="Double Hit",
        type="Normal",
        category="Physical",
        effects=["multi_hit:2"],
    )
    assert get_move_hit_count(move) == 2
    scaling = models.Move(
        name="Scale",
        type="Normal",
        category="Special",
        effects=["multi_hit:scaling:10,20,30"],
    )
    assert get_scaling_hit_powers(scaling) == [10, 20, 30]
    assert get_move_hit_count(scaling) == 3


def test_unit_flag_and_status_helpers(db):
    unit = models.GameUnit(flags={}, status_effects=[], states=[], stat_boosts={})
    assert get_unit_flags(unit) == {}
    set_unit_flags(unit, {"held_item": "leftovers"}, db)
    assert get_unit_held_item(unit) == "leftovers"
    set_unit_held_item(unit, "oran_berry", db)
    assert get_unit_held_item(unit) == "oran_berry"
    assert unit_has_status_condition(models.GameUnit(status_effects=["burn", 2])) is True
    assert unit_has_status_condition(models.GameUnit(status_effects=[])) is False
    assert unit_has_glaive_rush(models.GameUnit(states=["glaive_rush", 1])) is True
    assert unit_has_positive_stat_stage(
        models.GameUnit(stat_boosts={"attack": [{"magnitude": 1, "expires_turn": 4}]})
    ) is True


def test_preparation_item_allowed():
    game = models.Game(start_with_tms=False)
    tm = models.Item(category="tm", slug="tm01")
    berry = models.Item(category="berry", slug="oran_berry")
    assert preparation_item_allowed(tm, game) is False
    assert preparation_item_allowed(berry, game) is True
    game.start_with_tms = True
    assert preparation_item_allowed(tm, game) is True
