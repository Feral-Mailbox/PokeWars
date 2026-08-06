"""Wave 4 token-level coverage for combat ability edge paths."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.combat_abilities as ca


def _u(**kwargs):
    values = {
        "id": 1, "game_id": 10, "user_id": 1, "is_fainted": False,
        "flags": {}, "current_hp": 80,
        "current_stats": {
            "hp": 100, "attack": 80, "defense": 70, "sp_attack": 75,
            "sp_defense": 65, "speed": 60,
        },
        "current_x": 0, "current_y": 0, "stat_boosts": {},
        "states": None, "status_effects": [], "unit": SimpleNamespace(name="Testmon"),
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _db(units=()):
    db = MagicMock()
    query = db.query.return_value
    filtered = query.filter.return_value
    filtered.all.return_value = list(units)
    filtered.count.return_value = 2
    filtered.first.return_value = SimpleNamespace(id=99, name="Copied Ability", slug="copied")
    filtered.order_by.return_value.all.return_value = list(units)
    query.filter_by.return_value.first.return_value = None
    return db


def _move(**kwargs):
    data = {
        "id": 4, "name": "Tackle", "slug": "tackle", "type": "fire",
        "category": "physical", "power": 80, "effects": [], "makes_contact": True,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_switch_in_late_token_paths(monkeypatch):
    unit = _u(flags={"protean_used": True, "locked_move_id": 4})
    ally = _u(id=2, current_hp=10, stat_boosts={"attack": [{"magnitude": 2}]},
               unit=SimpleNamespace(name="Dondozo", species="dondozo"))
    foe = _u(id=3, user_id=2, flags={"ability_id": 7, "held_item": "orb"},
             current_stats={"attack": 101, "defense": 50, "sp_attack": 99,
                            "sp_defense": 50, "speed": 77})
    fainted = _u(id=4, is_fainted=True)
    db = _db([unit, ally, foe, fainted])
    tokens = [
        "on_switch_in:ally:heal_fraction:4",
        "on_switch_in:self:copy_stat_changes:ally",
        "on_switch_in:boost_power_per_fainted_ally:0.1:max:0.5",
        "on_switch_in:change_forme:terastal",
        "on_switch_in:enter_ally:dondozo",
        "on_switch_in:self:apply_state:slow_start:5",
        "on_switch_in:reveal:opponent_held_items",
        "on_switch_in:sense:super_effective",
        "on_switch_in:disguise_as:last_ally",
        "on_switch_in:transform:opponent",
        "permanent_status:sleep",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Wave Four"))
    monkeypatch.setattr(ca, "mark_just_switched_in", lambda *a: None)
    monkeypatch.setattr(ca, "apply_multitype_from_held_item", lambda *a: False)
    monkeypatch.setattr(ca, "apply_rks_from_held_item", lambda *a: False)
    monkeypatch.setattr(ca, "update_hp_threshold_formes", lambda *a: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a: False)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a: False)
    monkeypatch.setattr(ca, "_is_ability_suppressed", lambda *a: False)
    monkeypatch.setattr(
        ca, "ability_has_token", lambda u, d, *tokens, **k: "comatose" in tokens
    )
    monkeypatch.setattr(ca.random, "choice", lambda options: options[0])
    messages = ca.process_switch_in(
        unit, db, game=SimpleNamespace(id=10, link="wave4"),
        game_state=SimpleNamespace(), map_state=SimpleNamespace(weather_tiles=[[0]], terrain_effect_tiles=None),
        current_turn=1,
        helpers={
            "get_unit_types": lambda u, d: {"water"} if u is foe else {"normal"},
            "get_type_multiplier": lambda *a: 2.0,
            "set_unit_ability_id": lambda u, aid, d: ca._set_unit_flags(
                u, {**ca._unit_flags(u), "ability_id": aid}, d
            ),
        },
    )
    assert messages
    assert unit.flags["slow_start_remaining"] == 5
    assert unit.flags["commander_host_id"] == ally.id
    assert unit.status_effects == ["sleep", 999]


def test_end_of_turn_remaining_paths(monkeypatch):
    perish = _u(id=10, states=["perish", 1])
    unit = _u(
        id=11, current_hp=50, status_effects=["badly_poisoned", 3],
        flags={"slow_start_remaining": 1, "consumed_berry": "sitrus-berry",
               "last_consumed_berry": "sitrus-berry", "cud_chew_pending": True,
               "cud_chew_berry": "oran-berry"},
    )
    ally = _u(id=12, status_effects=["burn", 3])
    sleeping_foe = _u(id=13, user_id=2, status_effects=["sleep", 2], current_hp=70)
    db = _db([unit, ally, sleeping_foe])
    tokens = [
        "on_weather:sun:on_turn_end:self:recycle_berry:100",
        "on_status:poison:on_turn_end:self:heal_fraction:8",
        "on_turn_end:allies:cure_status:100",
        "on_turn_end:self:raise_random_stat:2",
        "on_turn_end:self:lower_other_random_stat:1",
        "on_turn_end:opponents:if_asleep:damage_fraction:8",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda u, *a, **k: [] if u is perish else tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Moody"))
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a: False)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a: False)
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a: False)
    monkeypatch.setattr(ca.random, "randint", lambda *a: 1)
    monkeypatch.setattr(ca.random, "choice", lambda values: list(values)[0])
    changed = ca.process_end_of_turn_abilities(
        [perish, unit], db, game=SimpleNamespace(id=10, link="end"),
        game_state=SimpleNamespace(), weather_tiles=[[ca.WEATHER_TO_ID["sun"]]],
        current_turn=3,
    )
    assert perish.is_fainted and perish.id in changed
    assert "slow_start_remaining" not in unit.flags
    assert unit.flags["held_item"] == "sitrus-berry"
    assert ally.status_effects == []


def test_stats_field_flower_and_ruin(monkeypatch):
    unit = _u(flags={"slow_start_remaining": 2, "unburden_boost": True, "forme": "zen"})
    flower = _u(id=2)
    ruin = _u(id=3, user_id=2)
    db = _db([unit, flower, ruin])
    def effects(subject, *args, **kwargs):
        if subject is flower:
            return ["on_weather:sun:allies:boost_stat_mult:attack:1.5", "plus"]
        if subject is ruin:
            return ["field_others:boost_stat_mult:defense:0.75"]
        return ["on_ally_ability:plus_or_minus:self:boost_stat_mult:sp_attack:1.5"]
    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "ability_has_token", lambda u, d, *t, **k: u is flower)
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a: False)
    monkeypatch.setattr(ca, "terrain_is_suppressed", lambda *a: False)
    monkeypatch.setattr(ca, "has_unburden_boost", lambda *a: True)
    monkeypatch.setattr(ca, "_protosynthesis_or_quark_boost", lambda *a, **k: ("speed", 1.3))
    result = ca.modify_effective_stats(
        unit, unit.current_stats, db, weather_tiles=[[ca.WEATHER_TO_ID["sun"]]],
        ally_units=[unit, flower],
    )
    assert result["attack"] < unit.current_stats["attack"] * 1.5
    assert result["sp_attack"] > unit.current_stats["sp_attack"]
    assert result["speed"] > unit.current_stats["speed"]


def test_defender_reaction_field_effects(monkeypatch):
    attacker = _u(id=1, user_id=1)
    defender = _u(id=2, user_id=2, current_hp=40)
    other = _u(id=3, user_id=1)
    db = _db([attacker, other])
    monkeypatch.setattr(
        ca, "get_ability_effects", lambda *a, **k: [
            "on_damage_taken:weather:sandstorm", "on_damage_taken:terrain:grassy",
            "on_damage_taken:others:lower_stat:speed:1",
            "on_damage_taken:attacker:status:burn",
            "on_hit_category:physical:field_hazard:toxic_spikes:2",
        ],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Sand Spit"))
    monkeypatch.setattr(ca, "can_apply_status", lambda *a: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda *a: False)
    monkeypatch.setattr(ca.random, "randint", lambda *a: 1)
    map_state = SimpleNamespace(weather_tiles=[[0]], terrain_effect_tiles=None)
    messages = ca.process_defender_hit_reactions(
        attacker, defender, _move(), damage=20, move_type="fire", is_physical=True,
        was_crit=False, db=db, current_turn=2, before_hp=90,
        helpers={"map_state": map_state, "place_field_hazard": lambda *a, **k: None},
    )
    assert messages and map_state.weather_tiles[0][0] == ca.WEATHER_TO_ID["sandstorm"]
    assert map_state.terrain_effect_tiles


def test_items_traps_status_and_absorb_edges(monkeypatch):
    attacker, target, ally = _u(id=1, flags={}), _u(id=2, user_id=2, current_x=1, flags={"held_item": "orb"}), _u(id=3, flags={"held_item": "berry"})
    db = _db([attacker, ally])
    monkeypatch.setattr(ca, "blocks_item_removal", lambda *a: False)
    monkeypatch.setattr(ca, "ability_has_token", lambda u, d, *tokens, **k: u is attacker or u is ally)
    assert ca.process_magician_steal(attacker, target, 10, db)
    attacker.flags.pop("held_item", None)
    assert ca.process_symbiosis_transfer(attacker, db)
    monkeypatch.setattr(ca, "_is_ability_suppressed", lambda *a: False)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["trap_opponents:grounded"])
    monkeypatch.setattr(ca, "ability_has_token", lambda u, d, *tokens, **k: False)
    ca.unit_traps_opponent(attacker, target, db, get_types=lambda u, d: {"steel"})
    db.query.return_value.filter.return_value.all.return_value = [attacker]
    ca.is_trapped_by_adjacent_opponent(target, db, get_types=lambda u, d: {"steel"})
    monkeypatch.setattr(ca, "ability_has_token", lambda u, d, *tokens, **k: u is attacker or u is ally)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["immune:fire", "on_hit:fire:self:heal_fraction:4"])
    target.current_hp = 20
    assert ca.handle_type_absorb(target, "fire", db)["absorbed"]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_weather:sun:immune_status:all"])
    monkeypatch.setattr(ca, "_lookup_unit_weather_tiles", lambda *a: [[ca.WEATHER_TO_ID["sun"]]])
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a: False)
    ca.can_apply_status(target, "burn", db)


def test_gen_nine_receiver_disguise_and_emergency(monkeypatch):
    db = _db()
    defender = _u(flags={}, current_hp=100)
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_disguise_break:self:damage_fraction:4"])
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Disguise"))
    assert ca.process_disguise(defender, 90, db)[0] == 25
    fainted = _u(id=5, is_fainted=True, flags={"ability_id": 42})
    receiver = _u(id=6, flags={})
    assert ca.process_receiver_on_ally_faint(fainted, [receiver], db)
    exit_unit = _u(current_hp=50, flags={})
    assert ca.process_emergency_exit_or_wimp_out(exit_unit, before_hp=80, db=db)
    proto = _u(flags={"held_item": "booster-energy", "booster_energy_active": True}, current_stats={"speed": 200})
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_weather:sun:boost_highest_stat:1.3"])
    assert ca._protosynthesis_or_quark_boost(proto, db, weather_id=0) == ("speed", 1.3)
    target = _u(status_effects=[], states=None)
    monkeypatch.setattr(ca, "can_apply_status", lambda *a: True)
    monkeypatch.setattr(ca, "can_apply_state", lambda *a: True)
    monkeypatch.setattr(ca.random, "randint", lambda *a: 1)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_damage_dealt:target:status:badly_poison:100"])
    assert ca.process_toxic_chain(proto, target, damage=5, db=db)
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.process_poison_puppeteer(proto, target, "badly_poisoned", db)


def test_redirect_aura_regenerator_and_ally_power(monkeypatch):
    attacker, redirector, aura = _u(id=1), _u(id=2, user_id=2), _u(id=3, user_id=2)
    db = _db([redirector, aura])
    def effects(unit, *args, **kwargs):
        if unit is redirector:
            return ["redirect:electric", "aura_break"]
        if unit is aura:
            return ["field:on_move_type:dark:boost_power:1.33", "allies:on_move_category:physical:boost_power:1.5"]
        return ["on_switch_out:self:heal_fraction:4"]
    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "ability_has_token", lambda u, d, *tokens, **k: "redirect:electric" in tokens and u is redirector)
    assert ca.redirect_targets_for_move(_move(type="electric"), attacker, [], [redirector], db) == [redirector]
    assert ca.field_move_type_power_multiplier(10, "dark", db) < 1
    attacker.current_hp = 20
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    assert ca.process_switch_out_or_faint(attacker, db)
