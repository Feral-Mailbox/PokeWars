"""Focused unit coverage for combat_abilities helpers under 90%."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.combat_abilities as ca
from app.move_traits import (
    MOVE_TRAIT_BALL_BOMB,
    MOVE_TRAIT_BITING,
    MOVE_TRAIT_POWDER,
    MOVE_TRAIT_PULSE,
    MOVE_TRAIT_PUNCHING,
    MOVE_TRAIT_SLICING,
    MOVE_TRAIT_SOUND,
    MOVE_TRAIT_WIND,
)


def _unit(**kwargs):
    defaults = {
        "id": 1,
        "game_id": 10,
        "user_id": 100,
        "is_fainted": False,
        "flags": {},
        "current_hp": 100,
        "current_stats": {"hp": 100},
        "current_x": 0,
        "current_y": 0,
        "stat_boosts": {},
        "states": None,
        "unit": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_get_unit_gender_from_flags_and_unit_info():
    assert ca._get_unit_gender(_unit(flags={"gender": "Male"})) == "male"
    assert ca._get_unit_gender(_unit(flags={"gender": "  "})) is None
    info = SimpleNamespace(gender="Female")
    assert ca._get_unit_gender(_unit(flags={}, unit=info)) == "female"
    assert ca._get_unit_gender(_unit(flags={}, unit=SimpleNamespace(gender=None))) is None


def test_weather_and_terrain_id_helpers():
    assert ca._weather_id_at(None, 0, 0) == 0
    assert ca._weather_id_at([[1]], -1, 0) == 0
    assert ca._weather_id_at([[1]], 0, 1) == 0
    assert ca._weather_id_at([["x"]], 0, 0) == 0
    assert ca._weather_id_at([[2]], 0, 0) == 2
    assert ca._weather_id_at([None], 0, 0) == 0

    assert ca._terrain_id_at([[[3, 5]]], 0, 0) == 3
    assert ca._terrain_id_at([[4]], 0, 0) == 4
    assert ca._terrain_id_at([["bad"]], 0, 0) == 0
    assert ca._terrain_id_at(None, 0, 0) == 0

    unit = _unit(current_x="bad", current_y=0)
    assert ca._unit_weather_id(unit, [[1]]) == 0
    unit2 = _unit(current_x=0, current_y=0)
    assert ca._unit_weather_id(unit2, [[5]]) == 5


def test_set_weather_and_terrain_on_map():
    map_state = SimpleNamespace(weather_tiles=[[0, 0], [0]])
    ca.set_weather_on_map(map_state, "rain")
    assert map_state.weather_tiles == [[2, 2], [2]]

    ca.set_weather_on_map(map_state, "not_a_weather")
    assert map_state.weather_tiles == [[2, 2], [2]]

    map_state2 = SimpleNamespace(weather_tiles=[[0, 0]], terrain_effect_tiles=None)
    ca.set_terrain_on_map(map_state2, "electric", duration=3)
    assert map_state2.terrain_effect_tiles == [[[1, 3], [1, 3]]]

    map_state3 = SimpleNamespace(terrain_effect_tiles=[[None, [0]], "bad"])
    ca.set_terrain_on_map(map_state3, "misty", duration="nope")
    assert map_state3.terrain_effect_tiles[0][1] == [4, ca.TERRAIN_DEFAULT_DURATION]
    assert map_state3.terrain_effect_tiles[1] == []


def test_get_battle_types_and_flash_fire():
    db = MagicMock()
    unit = _unit(flags={"battle_types": ["Fire", "Flying"]})
    assert ca.get_battle_types(unit, db) == {"fire", "flying"}
    unit2 = _unit(flags={})
    assert ca.get_battle_types(unit2, db, fallback_fn=lambda u, d: {"water"}) == {"water"}
    assert ca.has_flash_fire_boost(_unit(flags={"flash_fire_boost": True})) is True
    assert ca.has_flash_fire_boost(_unit(flags={})) is False


def test_update_forecast_types(monkeypatch):
    db = MagicMock()
    unit = _unit(flags={})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.update_forecast_types(unit, ca.WEATHER_TO_ID["rain"], db) is False

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_default_get_unit_types", lambda u, d: {"normal"})
    assert ca.update_forecast_types(unit, ca.WEATHER_TO_ID["rain"], db) is True
    assert unit.flags["battle_types"] == ["water"]

    assert ca.update_forecast_types(unit, ca.WEATHER_TO_ID["sun"], db) is True
    assert unit.flags["battle_types"] == ["fire"]

    assert ca.update_forecast_types(unit, ca.WEATHER_TO_ID["hail"], db) is True
    assert unit.flags["battle_types"] == ["ice"]

    assert ca.update_forecast_types(unit, 0, db) is True
    assert "battle_types" not in unit.flags


def test_move_trait_classifiers():
    punch = SimpleNamespace(move_trait=MOVE_TRAIT_PUNCHING, slug=None, name=None, effects=None)
    assert ca._move_is_punch(punch) is True
    assert ca._move_is_punch(SimpleNamespace(move_trait=0, slug="fire-punch", name="", effects=None))
    assert ca._move_is_punch(SimpleNamespace(move_trait=0, slug="x", name="Drain Punch", effects=None))

    assert ca._move_is_bite(SimpleNamespace(move_trait=MOVE_TRAIT_BITING, slug=None, name=None))
    assert ca._move_is_pulse(SimpleNamespace(move_trait=MOVE_TRAIT_PULSE, slug=None, name=None))
    assert ca._move_is_ball_bomb(SimpleNamespace(move_trait=MOVE_TRAIT_BALL_BOMB, slug=None, name=None))
    assert ca._move_is_slicing(SimpleNamespace(move_trait=MOVE_TRAIT_SLICING, slug=None, name=None))
    assert ca._move_is_wind(SimpleNamespace(move_trait=MOVE_TRAIT_WIND, slug=None, name=None))
    assert ca._move_is_sound(SimpleNamespace(move_trait=MOVE_TRAIT_SOUND, slug=None, name=None))
    assert ca._move_is_powder(SimpleNamespace(move_trait=MOVE_TRAIT_POWDER, slug=None, name=None))
    assert ca._move_is_powder(SimpleNamespace(move_trait=0, slug="sleep_powder", name="", effects=None))


def test_move_has_recoil_or_crash():
    assert ca._move_has_recoil_or_crash(SimpleNamespace(effects=None), "recoil") is False
    assert ca._move_has_recoil_or_crash(
        SimpleNamespace(effects=["self:recoil:33"]), "recoil"
    )
    assert ca._move_has_recoil_or_crash(
        SimpleNamespace(effects=["self:crash"]), "crash"
    )
    assert ca._move_has_recoil_or_crash(
        SimpleNamespace(effects=["failure_damage"]), "crash"
    )
    assert ca._move_has_recoil_or_crash(SimpleNamespace(effects=["nothing"]), "recoil") is False


def test_blocks_and_explosion_helpers(monkeypatch):
    db = MagicMock()
    defender = _unit()
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.blocks_ohko(defender, db) is True
    assert ca.blocks_sound_move(defender, db) is True
    assert ca.blocks_item_removal(defender, db) is True
    assert ca.prevents_opponent_berry_eat(defender, db) is True
    assert ca.is_klutz(defender, db) is True

    move = SimpleNamespace(slug="explosion", name="", effects=None)
    assert ca.move_is_explosion_like(move) is True
    assert ca.move_is_explosion_like(
        SimpleNamespace(slug="x", name="Self Destruct", effects=None)
    )
    assert ca.move_is_explosion_like(
        SimpleNamespace(slug="x", name="y", effects=["category:explosion"])
    )
    assert ca.move_is_explosion_like(SimpleNamespace(slug="tackle", name="", effects=[])) is False

    assert ca.blocks_explosion(0, db) is False
    living = [_unit(id=1), _unit(id=2)]
    db.query.return_value.filter.return_value.all.return_value = living
    assert ca.blocks_explosion(10, db) is True


def test_blocks_powder_move(monkeypatch):
    db = MagicMock()
    defender = _unit()
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.blocks_powder_move(defender, SimpleNamespace(move_trait=MOVE_TRAIT_POWDER), db) is False

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.blocks_powder_move(
        defender, SimpleNamespace(move_trait=MOVE_TRAIT_POWDER, slug=None, name=None, effects=None), db
    )
    assert ca.blocks_powder_move(
        defender,
        SimpleNamespace(move_trait=0, slug="x", name="y", effects=["category:powder"]),
        db,
    )
    assert (
        ca.blocks_powder_move(
            defender, SimpleNamespace(move_trait=0, slug="tackle", name="", effects=[]), db
        )
        is False
    )


def test_stab_crit_and_priority_helpers(monkeypatch):
    db = MagicMock()
    attacker = _unit()
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: [])
    assert ca.get_stab_multiplier(attacker, "fire", {"fire"}, db) == 1.5
    assert ca.get_stab_multiplier(attacker, "water", {"fire"}, db) == 1.0
    assert ca.crit_damage_multiplier(attacker, db) == 1.5
    assert ca.crit_stage_bonus(attacker, db) == 0
    assert ca.status_move_priority_bonus(attacker, db, SimpleNamespace(category="physical")) == 0
    assert ca.unit_weight_multiplier(attacker, db) == 1.0

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["adaptability"])
    assert ca.get_stab_multiplier(attacker, "fire", {"fire"}, db) == 2.0

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["boost_stab:1.8"])
    assert ca.get_stab_multiplier(attacker, "fire", {"fire"}, db) == 1.8

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["boost_stab:bad"])
    assert ca.get_stab_multiplier(attacker, "fire", {"fire"}, db) == 2.0

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["sniper"])
    assert ca.crit_damage_multiplier(attacker, db) == 2.25
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["boost_crit_damage:2.0"])
    assert ca.crit_damage_multiplier(attacker, db) == 2.0
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["boost_crit_damage:x"])
    assert ca.crit_damage_multiplier(attacker, db) == 2.25

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["super_luck"])
    assert ca.crit_stage_bonus(attacker, db) == 1
    monkeypatch.setattr(
        ca, "get_ability_effects", lambda *a, **k: ["self:raise_stat:crit:2"]
    )
    assert ca.crit_stage_bonus(attacker, db) == 2
    monkeypatch.setattr(
        ca, "get_ability_effects", lambda *a, **k: ["self:raise_stat:crit:bad"]
    )
    assert ca.crit_stage_bonus(attacker, db) == 1

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["prankster"])
    assert ca.status_move_priority_bonus(attacker, db, SimpleNamespace(category="status")) == 1
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["priority_status:2"])
    assert ca.status_move_priority_bonus(attacker, db) == 2
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["priority_status:x"])
    assert ca.status_move_priority_bonus(attacker, db) == 1

    monkeypatch.setattr(
        ca, "get_ability_effects", lambda *a, **k: ["self:boost_weight:2.0", "self:boost_weight:bad"]
    )
    assert ca.unit_weight_multiplier(attacker, db) == 2.0


def test_berry_hp_threshold_and_wonder_skin(monkeypatch):
    db = MagicMock()
    unit = _unit()
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: [])
    assert ca.berry_hp_threshold_percent(unit, db) == 25
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["gluttony"])
    assert ca.berry_hp_threshold_percent(unit, db) == 50
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["berry_threshold:40"])
    assert ca.berry_hp_threshold_percent(unit, db) == 40
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["berry_threshold:x"])
    assert ca.berry_hp_threshold_percent(unit, db) == 50

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.wonder_skin_accuracy_multiplier(unit, SimpleNamespace(category="status"), db) == 1.0
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.wonder_skin_accuracy_multiplier(unit, SimpleNamespace(category="physical"), db) == 1.0
    assert ca.wonder_skin_accuracy_multiplier(unit, SimpleNamespace(category="status"), db) == 0.5


def test_tinted_lens_and_scrappy(monkeypatch):
    db = MagicMock()
    attacker = _unit()
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.tinted_lens_multiplier(attacker, 0.5, db) == 1.0
    assert ca.tinted_lens_multiplier(attacker, 1.0, db) == 1.0
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.tinted_lens_multiplier(attacker, 0.5, db) == 0.5

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["scrappy"])
    assert ca.scrappy_allows_hit(attacker, "normal", {"ghost"}, db) is True
    assert ca.scrappy_allows_hit(attacker, "water", {"ghost"}, db) is False
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["hit_ghost_with:fighting"])
    assert ca.scrappy_allows_hit(attacker, "fighting", {"ghost"}, db) is True


def test_simple_type_multiplier():
    assert ca._simple_type_multiplier("normal", {"ghost"}) == 0.0
    assert ca._simple_type_multiplier("fire", {"grass"}) == 2.0
    assert ca._simple_type_multiplier("fire", {"water"}) == 0.5
    assert ca._simple_type_multiplier("electric", {"ground"}) == 0.0
    assert ca._simple_type_multiplier("unknown", {"normal"}) == 1.0


def test_attacker_accuracy_and_evasion(monkeypatch):
    db = MagicMock()
    attacker = _unit(id=1, game_id=10, user_id=100)
    ally = _unit(id=2, game_id=10, user_id=100)
    db.query.return_value.filter.return_value.all.return_value = [attacker, ally]

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda unit, db, _cache=None: (
            ["self:boost_accuracy:1.3", "on_move_category:physical:self:boost_accuracy:0.8"]
            if getattr(unit, "id", None) == 1
            else ["allies:boost_accuracy:1.1"]
        ),
    )
    mult = ca.attacker_accuracy_multiplier(
        attacker, SimpleNamespace(category="physical"), db
    )
    assert abs(mult - 1.3 * 0.8 * 1.1) < 1e-9

    defender = _unit(game_id=10, current_x=0, current_y=0, states=["confusion", 2])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_weather:sandstorm:self:boost_stat_mult:evasion:1.25",
            "on_status:confusion:self:boost_stat_mult:evasion:1.2",
        ],
    )
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    weather = [[ca.WEATHER_TO_ID["sandstorm"]]]
    ev = ca.defender_evasion_multiplier(defender, db, weather_tiles=weather)
    assert abs(ev - 1.25 * 1.2) < 1e-9


def test_extra_pp_cost_and_unnerve(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    targets = [_unit(is_fainted=False), None, _unit(is_fainted=True)]
    assert ca.extra_pp_cost_against(targets, db) == 1

    unit = _unit(game_id=10, user_id=1)
    opp = _unit(game_id=10, user_id=2)
    db.query.return_value.filter.return_value.all.return_value = [opp]
    assert ca.opponent_unnerve_blocks_berry(unit, db) is True
    assert ca.opponent_unnerve_blocks_berry(_unit(game_id=None, user_id=1), db) is False


def test_process_steadfast_and_dancer(monkeypatch):
    db = MagicMock()
    unit = _unit(id=1, flags={}, stat_boosts={})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.process_steadfast(unit, db, 1) == []

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_flinch:self:raise_stat:speed:2"],
    )
    msgs = ca.process_steadfast(unit, db, 3)
    assert msgs and "Steadfast" in msgs[0]
    assert unit.stat_boosts["speed"][0]["magnitude"] == 2

    dance = SimpleNamespace(
        slug="swords_dance",
        name="Swords Dance",
        effects=["self:raise_stat:attack:2"],
        move_trait=0,
    )
    user = _unit(id=10)
    dancer = _unit(id=11, flags={}, stat_boosts={})
    monkeypatch.setattr(ca, "is_dance_move", lambda m: True)
    out = ca.process_dancer_copy(dance, user, [user, dancer], db, 1)
    assert out and "Dancer" in out[0]
    assert dancer.stat_boosts["attack"][0]["magnitude"] == 2


def test_activate_booster_energy(monkeypatch):
    db = MagicMock()
    unit = _unit(flags={"held_item": "booster-energy"})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.activate_booster_energy(unit, db) is False

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.activate_booster_energy(_unit(flags={"held_item": "leftovers"}), db) is False
    unit2 = _unit(flags={"held_item": "Booster Energy"})
    assert ca.activate_booster_energy(unit2, db) is True
    assert unit2.flags.get("booster_energy_active") is True
    assert "held_item" not in unit2.flags


def test_apply_held_item_type_change(monkeypatch):
    db = MagicMock()
    unit = _unit(flags={})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_battle_types", lambda *a, **k: {"normal"})
    item = SimpleNamespace(boost_type="fire", effects=None, slug="flame-plate")
    changed = ca.apply_rks_from_held_item(
        unit,
        db,
        get_held_item_slug=lambda u: "flame-plate",
        resolve_item=lambda slug, database=None: item,
    )
    assert changed is True
    assert unit.flags["battle_types"] == ["fire"]

    monkeypatch.setattr(ca, "get_battle_types", lambda *a, **k: {"fire"})
    assert (
        ca.apply_multitype_from_held_item(
            unit,
            db,
            get_held_item_slug=lambda u, d=None: "flame-plate",
            resolve_item=lambda slug: item,
        )
        is False
    )

    item2 = SimpleNamespace(boost_type=None, effects=["on_move_type:water:boost"], slug="m")
    monkeypatch.setattr(ca, "get_battle_types", lambda *a, **k: {"normal"})
    assert ca._apply_held_item_type_change(
        unit, db, lambda u: "m", lambda slug, database=None: item2
    )


def test_terrain_suppressed_and_unburden(monkeypatch):
    db = MagicMock()
    assert ca.terrain_is_suppressed(0, db) is False
    unit = _unit(flags={"forme": "stellar"})
    db.query.return_value.filter.return_value.all.return_value = [unit]
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.terrain_is_suppressed(5, db) is True

    u2 = _unit(flags={})
    ca.mark_unburden(u2, db)
    assert u2.flags.get("unburden_boost") is True
    assert ca.has_unburden_boost(u2, db) is True
    u2.flags["held_item"] = "leftovers"
    assert ca.has_unburden_boost(u2, db) is False


def test_ability_protect_message(monkeypatch):
    db = MagicMock()
    unit = _unit(unit=SimpleNamespace(name="Bulbasaur"))
    move = SimpleNamespace(slug="ember", name="Ember", effects=None, move_trait=0)
    monkeypatch.setattr(ca, "should_block_move_against", lambda *a, **k: "soundproof")
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Soundproof"))
    msg = ca.ability_protect_message(unit, move, db)
    assert msg and "Soundproof" in msg

    monkeypatch.setattr(ca, "should_block_move_against", lambda *a, **k: "damp")
    assert ca.ability_protect_message(unit, move, db) == "Damp prevented the move!"

    monkeypatch.setattr(ca, "should_block_move_against", lambda *a, **k: None)
    monkeypatch.setattr(ca, "blocks_powder_move", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: None)
    msg2 = ca.ability_protect_message(unit, move, db, unit_name="Target")
    assert msg2 and "Overcoat" in msg2

    monkeypatch.setattr(ca, "blocks_powder_move", lambda *a, **k: False)
    assert ca.ability_protect_message(unit, move, db) is None


def test_can_apply_state_and_secondary_chance(monkeypatch):
    db = MagicMock()
    unit = _unit()
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["immune_flinch"])
    assert ca.can_apply_state(unit, "flinch", db) is False
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["immune_status:confusion"])
    assert ca.can_apply_state(unit, "confusion", db) is False
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["immune_status:infatuation"])
    assert ca.can_apply_state(unit, "attract", db) is False
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["immune_intimidate"])
    assert ca.can_apply_state(unit, "intimidate", db) is False
    assert ca.can_apply_state(unit, "", db) is False

    monkeypatch.setattr(ca, "_living_allies_including_self", lambda *a, **k: [unit])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["self_and_allies:immune_status:taunt"],
    )
    assert ca.can_apply_state(unit, "taunt", db) is False

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: [])
    assert ca.can_apply_state(unit, "flinch", db) is True

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["serene_grace"])
    assert ca.secondary_effect_chance_multiplier(unit, db) == 2.0
    monkeypatch.setattr(
        ca, "get_ability_effects", lambda *a, **k: ["self:boost_secondary_effect_chance:1.5"]
    )
    assert ca.secondary_effect_chance_multiplier(unit, db) == 1.5
    monkeypatch.setattr(
        ca, "get_ability_effects", lambda *a, **k: ["self:boost_secondary_effect_chance:x"]
    )
    assert ca.secondary_effect_chance_multiplier(unit, db) == 2.0


def test_misc_boolean_ability_helpers(monkeypatch):
    db = MagicMock()
    unit = _unit()
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.blocks_additional_effects(unit, db) is True
    assert ca.reverse_stat_changes(unit, db) is True
    assert ca.ignores_screens(unit, db) is True
    assert ca.ignores_safeguard(unit, db) is True
    assert ca.ignores_substitute(unit, db) is True
    assert ca.reflects_status_moves(unit, db) is True
    assert ca.immune_to_ally_attacks(unit, db) is True
    assert ca.should_ignore_target_ability(unit, db) is True
    assert ca.should_ignore_indirect_damage(unit, db) is True
    assert ca.should_ignore_weather_damage(unit, db) is True
    assert ca.should_ignore_poison_damage(unit, db) is True
    assert ca.should_halve_burn_damage(unit, db) is True
    assert ca.should_ignore_paralysis_speed(unit, db) is True
    assert ca.force_max_multi_hit(unit, db) is True
    assert ca.locks_first_selected_move(unit, db) is True
    assert ca.berry_effect_multiplier(unit, db) == 2.0
    assert ca.sleep_duration_multiplier(unit, db) == 0.5
    assert ca.force_move_never_miss(unit, None, db) is True


def test_truant_and_switch_out(monkeypatch):
    db = MagicMock()
    unit = _unit(flags={}, status_effects=["burn", 2], current_hp=30, current_stats={"hp": 90})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.should_skip_turn_due_to_truant(unit, db) is False

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.should_skip_turn_due_to_truant(unit, db) is False  # first action not loaf
    assert unit.flags.get("truant_loafing") is True
    assert ca.should_skip_turn_due_to_truant(unit, db) is True

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_switch_out:change_forme:hero"])
    monkeypatch.setattr(ca, "_has_any_status", lambda u: True)
    applied = ca.process_switch_out_or_faint(unit, db, fainted=False)
    assert applied is True
    assert unit.flags.get("forme") == "hero" or unit.status_effects == []


def test_anger_point_stench_color_drain(monkeypatch):
    db = MagicMock()
    defender = _unit(stat_boosts={})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_crit_received:self:raise_stat:attack:6"],
    )
    msgs = ca.process_anger_point(defender, was_crit=True, db=db, current_turn=1)
    assert msgs and "Anger Point" in msgs[0]

    attacker = _unit()
    target = _unit(states=None)
    monkeypatch.setattr(ca, "can_apply_state", lambda *a, **k: True)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_damage_dealt:target:apply_state:flinch:100"],
    )
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    assert ca.process_stench_flinch(attacker, target, 10, db) is True
    assert target.states == ["flinch", 1]

    monkeypatch.setattr(ca, "get_battle_types", lambda *a, **k: {"normal"})
    assert ca.process_color_change(defender, "water", db) is True

    atk = _unit(current_hp=50)
    tgt = _unit()
    monkeypatch.setattr(
        ca,
        "ability_has_token",
        lambda unit, db, *prefixes, **k: "liquid_ooze" in prefixes
        or any("liquid" in p for p in prefixes)
        or "on_drained" in str(prefixes),
    )
    # Liquid Ooze path: ability_has_token True for target
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    delta = ca.process_drain(atk, tgt, 20, db)
    assert delta < 0
    assert atk.current_hp == 30

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    atk2 = _unit(current_hp=50, current_stats={"hp": 100})
    assert ca.process_drain(atk2, tgt, 20, db) > 0


def test_apply_sturdy_and_stance_and_winds(monkeypatch):
    db = MagicMock()
    defender = _unit(current_hp=100)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["sturdy"])
    assert ca.apply_sturdy(defender, 150, True, False, db) == 99
    assert ca.apply_sturdy(defender, 150, True, True, db) == 0
    assert ca.apply_sturdy(defender, 0, True, False, db) == 0

    attacker = _unit(flags={})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert (
        ca.process_stance_change(
            attacker, SimpleNamespace(slug="kings_shield", name="", power=0, category="status"), db
        )
        == "shield"
    )
    assert (
        ca.process_stance_change(
            attacker, SimpleNamespace(slug="tackle", name="", power=40, category="physical"), db
        )
        == "blade"
    )

    assert ca.move_type_nullified_by_weather("fire", ca.WEATHER_TO_ID["heavy_rain"]) is True
    assert ca.move_type_nullified_by_weather("water", ca.WEATHER_TO_ID["harsh_sun"]) is True
    assert ca.move_type_nullified_by_weather("grass", ca.WEATHER_TO_ID["rain"]) is False

    flying = _unit()
    monkeypatch.setattr(ca, "_default_get_unit_types", lambda u, d: {"flying"})
    assert (
        ca.apply_strong_winds_type_modifier(
            flying, 2.0, ca.WEATHER_TO_ID["strong_winds"], db
        )
        == 1.0
    )


def test_attacker_power_multiplier_common_tokens(monkeypatch):
    db = MagicMock()
    attacker = _unit(
        current_hp=20,
        current_stats={"hp": 100},
        flags={"flash_fire_boost": True},
        game_id=None,
    )
    move = SimpleNamespace(type="fire", category="physical", power=40, effects=None, slug="ember")
    tokens = [
        "on_hp_below:33:on_move_type:fire:self:boost_power:1.5",
        "self:boost_power:1.5",
        "on_move_category:physical:self:boost_power:2",
        "on_move_power_lte:60:self:boost_power:1.5",
        "on_move_trait:punching:self:boost_power:1.2",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "convert_move_type", lambda *a, **k: None)
    monkeypatch.setattr(ca, "move_has_secondary_effects", lambda m: False)
    monkeypatch.setattr(ca, "_move_is_punch", lambda m: True)
    mult = ca.attacker_power_multiplier(attacker, move, db)
    assert mult > 1.0


def test_defender_damage_multiplier_resist(monkeypatch):
    db = MagicMock()
    defender = _unit(current_hp=100, current_stats={"hp": 100}, game_id=None)
    move = SimpleNamespace(type="fire", category="special", power=80, effects=None, slug="flamethrower")
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_move_category:special:self:resist:0.5", "on_hit_type:fire:self:resist:0.8"],
    )
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    mult = ca.defender_damage_multiplier(defender, move, "fire", 1.0, db)
    assert mult < 1.0


def test_update_mimicry_and_ice_face_hail(monkeypatch):
    db = MagicMock()
    unit = _unit(flags={})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_default_get_unit_types", lambda u, d: {"normal"})
    assert ca.update_mimicry_types(unit, ca.TERRAIN_TO_ID["electric"], db) is True
    assert unit.flags["battle_types"] == ["electric"]
    assert ca.update_mimicry_types(unit, ca.TERRAIN_TO_ID["psychic"], db) is True
    assert ca.update_mimicry_types(unit, ca.TERRAIN_TO_ID["grassy"], db) is True
    assert ca.update_mimicry_types(unit, ca.TERRAIN_TO_ID["misty"], db) is True
    assert ca.update_mimicry_types(unit, 0, db) is True
    assert "battle_types" not in unit.flags

    unit2 = _unit(flags={"forme": "noice"})
    assert ca.restore_ice_face_on_hail(unit2, ca.WEATHER_TO_ID["hail"], db) is True


def test_gorilla_tactics_and_tera_shell(monkeypatch):
    db = MagicMock()
    unit = _unit(flags={}, current_hp=100, current_stats={"hp": 100})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.enforce_gorilla_tactics_lock(unit, 5, db) is None
    assert unit.flags["locked_move_id"] == 5
    assert ca.enforce_gorilla_tactics_lock(unit, 5, db) is None
    assert ca.enforce_gorilla_tactics_lock(unit, 9, db) == 5

    assert ca.tera_shell_type_multiplier(unit, 2.0, db) == 0.5
    assert ca.tera_shell_type_multiplier(unit, 2.0, db, damaging=False) == 2.0


def test_activate_booster_and_quick_draw(monkeypatch):
    db = MagicMock()
    unit = _unit(flags={"held_item": "booster energy"})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.activate_booster_energy(unit, db) is True

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["quick_draw"])
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    assert ca.quick_draw_goes_first(unit, db) is True
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 100)
    assert ca.quick_draw_goes_first(unit, db) is False


def test_process_switch_in_weather_terrain_intimidate(monkeypatch):
    db = MagicMock()
    unit = _unit(
        id=1,
        game_id=10,
        user_id=1,
        flags={"protean_used": True, "locked_move_id": 3},
    )
    opp = _unit(id=2, game_id=10, user_id=2, stat_boosts={"attack": []})
    map_state = SimpleNamespace(
        weather_tiles=[[0, 0], [0, 0]],
        terrain_effect_tiles=None,
    )
    game = SimpleNamespace(id=10, link="sw-in")
    game_state = SimpleNamespace()

    tokens = [
        "on_switch_in:weather:rain",
        "on_switch_in:terrain:electric",
        "on_switch_in:opponents:lower_stat:attack:1",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Drizzle"))
    monkeypatch.setattr(ca, "immune_to_intimidate", lambda *a, **k: False)
    monkeypatch.setattr(ca, "blocks_stat_drop", lambda *a, **k: False)
    monkeypatch.setattr(ca, "mark_just_switched_in", lambda *a, **k: None)
    db.query.return_value.filter.return_value.all.return_value = [opp]

    msgs = ca.process_switch_in(
        unit,
        db,
        game=game,
        game_state=game_state,
        map_state=map_state,
        current_turn=1,
    )
    assert any("rain" in m.lower() for m in msgs)
    assert any("electric" in m.lower() for m in msgs)
    assert any("attack" in m.lower() for m in msgs)
    assert "protean_used" not in unit.flags
    assert "locked_move_id" not in unit.flags


def test_process_contact_rough_skin_and_status(monkeypatch):
    db = MagicMock()
    attacker = _unit(id=1, current_hp=80, current_stats={"hp": 80}, stat_boosts={}, flags={"gender": "male"})
    defender = _unit(id=2, flags={"gender": "female", "ability_id": 9})
    tokens = [
        "on_contact:attacker:damage_fraction:8",
        "on_contact:attacker:lower_stat:speed:1",
        "on_contact:attacker:status:paralysis:100",
        "on_contact:both:apply_state:perish:3",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Rough Skin"))
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)

    msgs = ca.process_contact_abilities(
        attacker, defender, makes_contact=True, damage=10, db=db
    )
    assert msgs
    assert attacker.current_hp < 80
    assert "speed" in (attacker.stat_boosts or {})


def test_process_end_of_turn_speed_boost_and_perish(monkeypatch):
    db = MagicMock()
    unit = _unit(
        id=7,
        current_hp=50,
        current_stats={"hp": 100},
        flags={"slow_start_remaining": 2, "forme": "full_belly"},
        states=["perish", 3],
        stat_boosts={},
        status_effects=["burn", 2],
    )
    game = SimpleNamespace(id=10, link="eot")
    game_state = SimpleNamespace()
    weather = [[ca.WEATHER_TO_ID["rain"]]]

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_turn_end:self:raise_stat:speed:1",
            "on_turn_end:toggle_forme:full_belly_hangry",
            "on_turn_end:self:cure_status:100",
            "on_weather:rain:on_turn_end:self:heal_fraction:16",
        ],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Speed Boost"))
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: False)
    monkeypatch.setattr(ca, "process_cud_chew_end_of_turn", lambda *a, **k: [])
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)

    mutated = ca.process_end_of_turn_abilities(
        [unit, None, _unit(is_fainted=True)],
        db,
        game=game,
        game_state=game_state,
        weather_tiles=weather,
        current_turn=2,
    )
    assert 7 in mutated
    assert unit.states == ["perish", 2]
    assert "speed" in (unit.stat_boosts or {})
    assert unit.flags.get("forme") == "hangry"
    assert unit.status_effects == []
    assert unit.current_hp > 50


def test_process_on_ko_moxie_and_battle_bond(monkeypatch):
    db = MagicMock()
    attacker = _unit(
        id=1,
        user_id=1,
        flags={},
        stat_boosts={},
        current_stats={"attack": 50, "defense": 40, "sp_attack": 30, "sp_defense": 20, "speed": 10},
    )
    fainted = _unit(id=2, user_id=2)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_ko:self:raise_stat:attack:1", "on_ko:change_forme:ash", "on_ko:self:raise_stat:highest:1"],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Moxie"))
    msgs = ca.process_on_ko(attacker, fainted, db, 1)
    assert msgs
    assert attacker.flags.get("forme") == "ash"
    assert "attack" in (attacker.stat_boosts or {})


def test_process_end_of_turn_sun_damage(monkeypatch):
    db = MagicMock()
    unit = _unit(id=8, current_hp=80, current_stats={"hp": 100}, flags={})
    game = SimpleNamespace(id=10, link="eot-sun")
    weather = [[ca.WEATHER_TO_ID["sun"]]]
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_weather:sun:on_turn_end:self:damage_fraction:8"],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Dry Skin"))
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: False)
    monkeypatch.setattr(ca, "process_cud_chew_end_of_turn", lambda *a, **k: [])
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a, **k: False)

    mutated = ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=game,
        game_state=SimpleNamespace(),
        weather_tiles=weather,
        current_turn=1,
    )
    assert 8 in mutated
    assert unit.current_hp < 80
