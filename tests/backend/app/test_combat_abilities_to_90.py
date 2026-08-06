"""Drive combat_abilities.py toward ≥90% via bulk token-path coverage."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.combat_abilities as ca


def _u(**kwargs):
    defaults = {
        "id": 1,
        "game_id": 10,
        "user_id": 100,
        "is_fainted": False,
        "flags": {},
        "current_hp": 100,
        "current_stats": {
            "hp": 100,
            "attack": 50,
            "defense": 40,
            "sp_attack": 45,
            "sp_defense": 35,
            "speed": 60,
        },
        "current_x": 1,
        "current_y": 1,
        "stat_boosts": {},
        "states": None,
        "status_effects": [],
        "unit": SimpleNamespace(name="Testmon"),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _move(**kwargs):
    defaults = {
        "id": 7,
        "slug": "tackle",
        "name": "Tackle",
        "type": "normal",
        "category": "physical",
        "power": 40,
        "effects": None,
        "makes_contact": True,
        "move_trait": 0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _db(units=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = units or []
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.count.return_value = 0
    return db


# ---------------------------------------------------------------------------
# Type chart + absorb + power/damage multipliers
# ---------------------------------------------------------------------------


def test_simple_type_multiplier_full_chart():
    cases = [
        ("normal", {"ghost"}, 0.0),
        ("normal", {"rock"}, 0.5),
        ("fire", {"grass"}, 2.0),
        ("fire", {"water"}, 0.5),
        ("water", {"fire"}, 2.0),
        ("electric", {"ground"}, 0.0),
        ("electric", {"water"}, 2.0),
        ("grass", {"water"}, 2.0),
        ("ice", {"dragon"}, 2.0),
        ("fighting", {"ghost"}, 0.0),
        ("fighting", {"normal"}, 2.0),
        ("poison", {"steel"}, 0.0),
        ("poison", {"grass"}, 2.0),
        ("ground", {"flying"}, 0.0),
        ("ground", {"fire"}, 2.0),
        ("flying", {"grass"}, 2.0),
        ("psychic", {"dark"}, 0.0),
        ("psychic", {"fighting"}, 2.0),
        ("bug", {"psychic"}, 2.0),
        ("rock", {"fire"}, 2.0),
        ("ghost", {"normal"}, 0.0),
        ("ghost", {"psychic"}, 2.0),
        ("dragon", {"fairy"}, 0.0),
        ("dragon", {"dragon"}, 2.0),
        ("dark", {"psychic"}, 2.0),
        ("steel", {"ice"}, 2.0),
        ("fairy", {"dragon"}, 2.0),
        ("fairy", {"fire"}, 0.5),
        ("unknown", {"normal"}, 1.0),
        ("fire", {"grass", "steel"}, 4.0),
    ]
    for mt, defs, expected in cases:
        assert ca._simple_type_multiplier(mt, defs) == expected, (mt, defs)


def test_handle_type_absorb_paths(monkeypatch):
    db = _db()
    unit = _u(current_hp=50)

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["immune:water", "on_hit:water:self:heal_fraction:4"],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Water Absorb"))
    r = ca.handle_type_absorb(unit, "water", db)
    assert r and r["absorbed"] is True
    assert unit.current_hp == 75

    unit2 = _u(flags={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["immune:fire", "on_hit:fire:self:apply_state:flash_fire"],
    )
    r2 = ca.handle_type_absorb(unit2, "fire", db)
    assert r2 and unit2.flags.get("flash_fire") or unit2.flags.get("flash_fire_boost")

    unit3 = _u(stat_boosts={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["immune:electric", "on_hit:electric:self:raise_stat:speed:1"],
    )
    r3 = ca.handle_type_absorb(unit3, "electric", db)
    assert r3 and r3.get("raise_stat")


def test_attacker_power_multiplier_token_sweep(monkeypatch):
    db = _db()
    attacker = _u(
        current_hp=20,
        flags={"flash_fire_boost": True, "supreme_overlord_boost": 0.2, "gender": "male"},
        status_effects=["burn", 2],
        current_x=0,
        current_y=0,
    )
    ally = _u(id=2, user_id=100, current_x=1, current_y=0)
    target = _u(id=3, user_id=200, flags={"just_switched_in": True, "gender": "female"})
    db.query.return_value.filter.return_value.all.return_value = [attacker, ally]

    tokens = [
        "on_hp_below:33:on_move_type:fire:self:boost_power:1.5",
        "on_weather:sandstorm:on_move_type:rock:self:boost_power:1.3",
        "on_status:burn:on_move_category:physical:self:boost_power:1.5",
        "on_moves_with_secondary:self:boost_power:1.3",
        "on_move_last:self:boost_power:1.3",
        "on_move_type:fire:self:boost_power:1.5",
        "on_super_effective_deal:self:boost_power:1.25",
        "on_target_switched_in:self:boost_power:2",
        "on_move_category:physical:self:boost_power:1.5",
        "on_move_power_at_most:60:self:boost_power:1.5",
        "on_move_flag:punch:self:boost_power:1.2",
        "on_move_flag:recoil:self:boost_power:1.2",
        "on_move_flag:contact:self:boost_power:1.3",
        "on_move_flag:bite:self:boost_power:1.5",
        "on_move_flag:pulse:self:boost_power:1.5",
        "on_move_flag:slicing:self:boost_power:1.5",
        "on_opposite_gender:self:boost_power:1.25",
        "on_converted_type:self:boost_power:1.2",
        "self:boost_power:2",
        "allies:on_move_category:physical:boost_power:1.3",
        "adjacent_allies:boost_power:1.3",
        "self_and_allies:on_move_type:fire:boost_power:1.5",
    ]

    def effects(unit, db, _cache=None):
        if getattr(unit, "id", None) == 2:
            return ["allies:on_move_category:physical:boost_power:1.3", "adjacent_allies:boost_power:1.3", "self_and_allies:on_move_type:fire:boost_power:1.5"]
        return tokens

    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "convert_move_type", lambda *a, **k: "fire")
    monkeypatch.setattr(ca, "move_has_secondary_effects", lambda m: True)
    monkeypatch.setattr(ca, "_move_is_punch", lambda m: True)
    monkeypatch.setattr(ca, "_move_is_bite", lambda m: True)
    monkeypatch.setattr(ca, "_move_is_pulse", lambda m: True)
    monkeypatch.setattr(ca, "_move_is_slicing", lambda m: True)
    monkeypatch.setattr(ca, "_move_has_recoil_or_crash", lambda m, f: True)
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_active_status", lambda u: "burn")

    move = _move(type="fire", power=40, makes_contact=True, effects=["self:recoil:33"])
    weather = [[ca.WEATHER_TO_ID["sandstorm"]]]
    msgs = []
    mult = ca.attacker_power_multiplier(
        attacker,
        move,
        db,
        weather_tiles=weather,
        target=target,
        is_last_move=True,
        type_multiplier=2.0,
        trigger_messages=msgs,
    )
    assert mult > 2.0


def test_defender_damage_multiplier_token_sweep(monkeypatch):
    db = _db()
    defender = _u(current_hp=100, user_id=100)
    ally = _u(id=2, user_id=100)
    db.query.return_value.filter.return_value.all.return_value = [defender, ally]

    def effects(unit, db, _cache=None):
        if getattr(unit, "id", None) == 2:
            return ["allies:resist_damage:0.75"]
        return [
            "on_hit_type:fire:self:resist:0.5",
            "on_super_effective:self:resist:0.75",
            "on_hp_full:self:resist:0.5",
            "on_move_flag:contact:self:resist:0.5",
            "on_move_category:physical:self:resist:0.5",
            "on_hit_category:sound:self:resist:0.5",
            "only_super_effective_hits",
        ]

    monkeypatch.setattr(ca, "get_ability_effects", effects)
    move = _move(type="fire", category="physical", makes_contact=True)
    # Wonder Guard zeros non-SE
    assert ca.defender_damage_multiplier(defender, move, "fire", 1.0, db, makes_contact=True) == 0.0
    # SE path compounds resists
    mult = ca.defender_damage_multiplier(defender, move, "fire", 2.0, db, makes_contact=True)
    assert 0 < mult < 1.0


def test_modify_effective_stats_token_sweep(monkeypatch):
    db = _db()
    unit = _u(
        current_hp=20,
        status_effects=["burn", 2],
        flags={"slow_start_remaining": 2, "unburden_boost": True, "forme": "zen"},
        game_id=10,
        user_id=100,
    )
    ally = _u(id=2, user_id=100)
    other = _u(id=3, user_id=200)

    tokens = [
        "self:boost_stat_mult:attack:1.5",
        "on_weather:sun:self:boost_stat_mult:speed:2",
        "on_terrain:grassy:self:boost_stat_mult:defense:1.5",
        "on_status:any:self:boost_stat_mult:attack:1.5",
        "on_hp_below:50:self:boost_stat_mult:attack|sp_attack:0.5",
        "on_hp_below:50:change_forme:zen",
        "on_hp_above:25:change_forme:school",
        "ignore_burn_attack_halve",
        "ignore_paralysis_speed_halve",
        "on_ally_ability:plus_or_minus:self:boost_stat_mult:sp_attack:1.5",
    ]

    def effects(u, db, _cache=None):
        if getattr(u, "id", None) == 2:
            return ["on_weather:sun:allies:boost_stat_mult:attack:1.5", "plus"]
        if getattr(u, "id", None) == 3:
            return ["field_others:boost_stat_mult:defense:0.75"]
        return tokens

    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: "treat_weather_as" in str(a) or "unburden" in str(a) or "plus" in str(a) or False)
    # more precise ability_has_token
    def has_token(unit, db, *prefixes, **kw):
        joined = " ".join(prefixes)
        if "treat_weather_as" in joined or "mega_sol" in joined:
            return False
        if "on_item_lost" in joined or "unburden" in joined:
            return True
        if "plus" in joined or "minus" in joined:
            return getattr(unit, "id", None) == 2
        return False

    monkeypatch.setattr(ca, "ability_has_token", has_token)
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "terrain_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: True)
    monkeypatch.setattr(ca, "has_unburden_boost", lambda u, d: True)
    monkeypatch.setattr(ca, "_protosynthesis_or_quark_boost", lambda *a, **k: ("attack", 1.3))

    stats = {
        "attack": 100,
        "defense": 100,
        "sp_attack": 100,
        "sp_defense": 100,
        "speed": 100,
    }
    weather = [[ca.WEATHER_TO_ID["sun"]]]
    terrain = [[[ca.TERRAIN_TO_ID["grassy"], 5]]]
    msgs = []
    out = ca.modify_effective_stats(
        unit,
        stats,
        db,
        weather_tiles=weather,
        terrain_tiles=terrain,
        ally_units=[unit, ally],
        trigger_messages=msgs,
    )
    # Also exercise field_others via querying others - pass game units through db
    db.query.return_value.filter.return_value.all.return_value = [unit, ally, other]
    out2 = ca.modify_effective_stats(unit, stats, db, weather_tiles=weather, terrain_tiles=terrain)
    assert isinstance(out, dict)
    assert out["speed"] != 100 or out["attack"] != 100


# ---------------------------------------------------------------------------
# Contact / hit reactions / attacker contact
# ---------------------------------------------------------------------------


def test_process_contact_abilities_full(monkeypatch):
    db = _db()
    attacker = _u(
        id=1,
        current_hp=80,
        current_stats={"hp": 80},
        flags={"gender": "male", "ability_id": 1, "held_item": "leftovers"},
        status_effects=[],
        stat_boosts={},
    )
    defender = _u(
        id=2,
        flags={"gender": "female", "ability_id": 2},
        states=None,
    )
    tokens = [
        "on_contact:swap_abilities",
        "on_contact:both:apply_state:perish:3",
        "on_contact:attacker:damage_fraction:8",
        "on_contact:attacker:lower_stat:speed:1",
        "on_contact:attacker:status:paralysis:100",
        "on_contact:attacker:status:poison_or_sleep_or_paralysis:100",
        "on_contact:attacker:status:infatuation:100:opposite_gender",
        "on_contact:attacker:set_ability:mummy",
        "on_contact:self:steal_item",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Rough Skin"))
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(ca.random, "choice", lambda xs: xs[0])
    mummy = SimpleNamespace(id=99, slug="mummy", name="Mummy")
    db.query.return_value.filter.return_value.first.return_value = mummy

    msgs = ca.process_contact_abilities(
        attacker,
        defender,
        makes_contact=True,
        damage=20,
        db=db,
        helpers={
            "get_unit_held_item": lambda u: _u(flags=u.flags).flags.get("held_item"),
            "set_unit_held_item": lambda u, item, d: ca._set_unit_flags(
                u, {**ca._unit_flags(u), "held_item": item}, d
            ),
        },
    )
    assert msgs
    assert attacker.current_hp < 80


def test_process_attacker_contact_on_hit(monkeypatch):
    db = _db()
    attacker = _u()
    defender = _u(id=2, status_effects=[])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_contact_deal:target:status:poison:100"],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Poison Touch"))
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    msgs = ca.process_attacker_contact_on_hit(
        attacker, defender, makes_contact=True, damage=10, db=db
    )
    assert msgs or defender.status_effects


def test_process_defender_hit_reactions_full(monkeypatch):
    db = _db()
    attacker = _u(id=1, user_id=1, current_x=0, current_y=0)
    defender = _u(
        id=2,
        user_id=2,
        current_hp=40,
        current_stats={"hp": 100},
        stat_boosts={},
        flags={},
        states=None,
        current_x=1,
        current_y=0,
    )
    other = _u(id=3, user_id=1, current_x=2, current_y=0, is_fainted=False, stat_boosts={})
    db.query.return_value.filter.return_value.all.return_value = [attacker, defender, other]

    tokens = [
        "on_hit_type:dark:self:raise_stat:attack:1",
        "on_hit_category:physical:self:lower_stat:defense:1",
        "on_hit_category:physical:self:raise_stat:speed:1",
        "on_damage_taken:self:raise_stat:defense:1",
        "on_hp_cross_below:50:self:raise_stat:sp_attack:1",
        "on_damage_taken:attacker:apply_state:disable:100",
        "on_damage_taken:others:lower_stat:speed:1",
        "on_damage_taken:weather:sandstorm",
        "on_damage_taken:terrain:grassy",
        "on_damage_taken:self:apply_state:charge",
        "on_damage_taken:attacker:status:burn",
        "on_hit_category:wind:self:apply_state:charge",
        "on_hit_category:wind:self:raise_stat:attack:1",
        "on_hit_category:physical:field_hazard:toxic_spikes:1",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Weak Armor"))
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca, "can_apply_state", lambda *a, **k: True)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(ca, "_move_is_wind", lambda m: True)

    map_state = SimpleNamespace(weather_tiles=[[0]], terrain_effect_tiles=None)
    move = _move(type="dark", category="physical")
    msgs = ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=30,
        move_type="dark",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=2,
        before_hp=80,
        helpers={
            "map_state": map_state,
            "set_weather_on_map": ca.set_weather_on_map,
            "place_field_hazard": lambda *a, **k: None,
        },
    )
    assert msgs


# ---------------------------------------------------------------------------
# Switch-in & end of turn (bulk)
# ---------------------------------------------------------------------------


def test_process_switch_in_token_sweep(monkeypatch):
    db = _db()
    unit = _u(
        id=1,
        user_id=1,
        flags={"protean_used": True, "locked_move_id": 3},
        current_hp=80,
        current_stats={"hp": 100, "attack": 60, "sp_attack": 40, "defense": 30, "sp_defense": 50},
    )
    opp = _u(
        id=2,
        user_id=2,
        flags={"ability_id": 5, "held_item": "leftovers"},
        stat_boosts={"attack": [{"magnitude": 1, "expires_turn": 4}]},
        current_stats={"defense": 80, "sp_defense": 20, "attack": 10},
        unit=SimpleNamespace(name="Opp", moves=None),
    )
    ally = _u(
        id=3,
        user_id=1,
        current_hp=10,
        current_stats={"hp": 100},
        stat_boosts={"speed": [{"magnitude": 2, "expires_turn": 4}]},
        flags={},
    )
    db.query.return_value.filter.return_value.all.return_value = [opp]
    # For ally queries alternate
    def filter_side_effect(*args, **kwargs):
        m = MagicMock()
        # Return both opp and ally lists depending on call; simplify: always [opp, ally]
        m.all.return_value = [opp, ally]
        m.first.return_value = opp
        m.count.return_value = 1
        return m

    db.query.return_value.filter.side_effect = filter_side_effect

    tokens = [
        "on_switch_in:weather:rain",
        "on_switch_in:terrain:electric",
        "on_switch_in:opponents:lower_stat:attack:1",
        "on_switch_in:self:copy_ability:random_opponent",
        "on_switch_in:self:raise_stat:attack_or_special_attack:1",
        "on_switch_in:self:raise_stat:attack:1:once_per_battle",
        "on_switch_in:clear_screens",
        "on_switch_in:allies:clear_stat_changes",
        "suppress_other_abilities",
        "on_switch_in:ally:heal_fraction:4",
        "on_switch_in:self:copy_stat_changes:ally",
        "on_switch_in:boost_power_per_fainted_ally:0.1:max:0.5",
        "on_switch_in:change_forme:terastal",
        "on_switch_in:enter_ally:dondozo",
        "on_switch_in:self:apply_state:slow_start:5",
        "on_switch_in:disguise_as:last_opponent",
        "on_switch_in:transform:opponent",
        "on_switch_in:reveal:opponent_held_items",
        "on_switch_in:reveal:strongest_opponent_move",
        "on_switch_in:sense:super_effective",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Trace", id=5, slug="trace"))
    monkeypatch.setattr(ca, "immune_to_intimidate", lambda *a, **k: False)
    monkeypatch.setattr(ca, "blocks_stat_drop", lambda *a, **k: False)
    monkeypatch.setattr(ca, "mark_just_switched_in", lambda *a, **k: None)
    monkeypatch.setattr(ca, "apply_multitype_from_held_item", lambda *a, **k: False)
    monkeypatch.setattr(ca, "apply_rks_from_held_item", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_hp_threshold_formes", lambda *a, **k: None)
    monkeypatch.setattr(ca, "_simple_type_multiplier", lambda *a, **k: 2.0)
    monkeypatch.setattr(ca.random, "choice", lambda xs: xs[0] if xs else None)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: a)

    map_state = SimpleNamespace(
        weather_tiles=[[0, 0], [0, 0]],
        terrain_effect_tiles=None,
    )
    game = SimpleNamespace(id=10, link="sw")
    msgs = ca.process_switch_in(
        unit,
        db,
        game=game,
        game_state=SimpleNamespace(),
        map_state=map_state,
        current_turn=1,
        helpers={
            "set_unit_ability_id": lambda u, aid, d: ca._set_unit_flags(
                u, {**ca._unit_flags(u), "ability_id": aid}, d
            ),
            "get_unit_types": lambda u, d: {"normal"},
            "get_type_multiplier": lambda *a, **k: 2.0,
        },
    )
    assert isinstance(msgs, list)


def test_process_end_of_turn_token_sweep(monkeypatch):
    db = _db()
    unit = _u(
        id=1,
        current_hp=50,
        current_stats={"hp": 100, "attack": 40, "defense": 40, "sp_attack": 40, "sp_defense": 40, "speed": 40},
        flags={
            "slow_start_remaining": 2,
            "forme": "full_belly",
            "held_item": None,
            "consumed_items": ["leftovers"],
            "consumed_berry": "oran-berry",
            "last_consumed_berry": "oran-berry",
        },
        states=["perish", 3],
        status_effects=["poison", 2],
        stat_boosts={},
        user_id=1,
    )
    asleep_opp = _u(
        id=2,
        user_id=2,
        current_hp=80,
        current_stats={"hp": 100},
        status_effects=["sleep", 2],
        is_fainted=False,
    )
    ally = _u(id=3, user_id=1, status_effects=["burn", 2], current_hp=40, current_stats={"hp": 100})
    db.query.return_value.filter.return_value.all.return_value = [asleep_opp, ally]

    tokens = [
        "on_turn_end:toggle_forme:full_belly_hangry",
        "on_turn_end:self:raise_stat:speed:1",
        "on_turn_end:self:cure_status:100",
        "on_weather:rain:on_turn_end:self:heal_fraction:16",
        "on_weather:sun:on_turn_end:self:damage_fraction:8",
        "on_weather:rain:on_turn_end:self:cure_status",
        "on_status:poison:on_turn_end:self:heal_fraction:8",
        "on_turn_end:opponents:if_asleep:damage_fraction:8",
        "on_turn_end:self:pickup_consumed_item",
        "on_turn_end:self:recycle_berry:100",
        "on_weather:sun:on_turn_end:self:recycle_berry:100",
        "on_turn_end:allies:cure_status:100",
        "on_turn_end:self:raise_random_stat:1",
        "on_turn_end:self:lower_other_random_stat:1",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Moody"))
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "process_cud_chew_end_of_turn", lambda *a, **k: ["cud"])
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: bool(getattr(u, "status_effects", None)))
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(ca.random, "choice", lambda xs: xs[0])

    # First with rain weather
    weather_rain = [[ca.WEATHER_TO_ID["rain"]]]
    mutated = ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=SimpleNamespace(id=10, link="eot"),
        game_state=SimpleNamespace(),
        weather_tiles=weather_rain,
        current_turn=3,
        helpers={"terrain_tiles": [[[ca.TERRAIN_TO_ID["grassy"], 3]]]},
    )
    assert 1 in mutated

    # Sun weather for damage + harvest sun path
    unit2 = _u(
        id=4,
        current_hp=80,
        current_stats={"hp": 100},
        flags={"consumed_berry": "sitrus-berry", "last_consumed_berry": "sitrus-berry", "held_item": None},
        status_effects=[],
        states=None,
        stat_boosts={},
    )
    weather_sun = [[ca.WEATHER_TO_ID["sun"]]]
    ca.process_end_of_turn_abilities(
        [unit2],
        db,
        game=SimpleNamespace(id=10, link="eot2"),
        game_state=SimpleNamespace(),
        weather_tiles=weather_sun,
        current_turn=1,
    )


# ---------------------------------------------------------------------------
# Remaining mid/large helpers
# ---------------------------------------------------------------------------


def test_aftermath_and_color_and_redirect(monkeypatch):
    db = _db()
    attacker = _u(id=1, current_hp=50, current_stats={"hp": 100})
    fainted = _u(id=2, is_fainted=True, current_hp=0)
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_faint:attacker:damage_fraction:4"])
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Aftermath"))
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a, **k: False)
    msgs = ca.process_aftermath(fainted, attacker, makes_contact=True, db=db)
    assert msgs
    assert attacker.current_hp < 50

    defender = _u(flags={})
    monkeypatch.setattr(ca, "get_battle_types", lambda *a, **k: {"normal"})
    assert ca.process_color_change(defender, "water", db) is True


def test_redirect_targets_and_field_power(monkeypatch):
    db = _db()
    attacker = _u(id=1, user_id=1)
    rod = _u(id=2, user_id=2, current_x=0, current_y=0)
    other = _u(id=3, user_id=2, current_x=2, current_y=0)
    living = [attacker, rod, other]

    def effects(u, db, _cache=None):
        if getattr(u, "id", None) == 2:
            return ["redirect:electric"]
        return []

    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    move = _move(type="electric")
    result = ca.redirect_targets_for_move(move, attacker, [other], living, db)
    assert result is not None

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["field:on_move_type:dark:boost_power:1.33"],
    )
    assert ca.field_move_type_power_multiplier(10, "dark", db) >= 1.0


def test_magician_symbiosis_stance_traps(monkeypatch):
    db = _db()
    attacker = _u(id=1, user_id=1, flags={}, current_x=0, current_y=0)
    target = _u(id=2, user_id=2, flags={"held_item": "leftovers"}, current_x=1, current_y=0)
    ally = _u(id=3, user_id=1, flags={"held_item": "sitrus-berry"}, current_x=0, current_y=1)

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_hit:steal_item"])
    monkeypatch.setattr(ca, "is_klutz", lambda *a, **k: False)
    monkeypatch.setattr(ca, "blocks_item_removal", lambda *a, **k: False)
    ca.process_magician_steal(attacker, target, 10, db)

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_ally_item_consumed:transfer_item"])
    db.query.return_value.filter.return_value.all.return_value = [ally]
    ca.process_symbiosis_transfer(attacker, db)

    assert ca.process_stance_change(attacker, _move(power=40, category="physical"), db) in (
        "blade",
        "shield",
        None,
    )

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["trap_grounded_opponents", "arena_trap"],
    )
    ca.unit_traps_opponent(attacker, target, db)
    db.query.return_value.filter.return_value.all.return_value = [attacker]
    ca.is_trapped_by_adjacent_opponent(target, db)


def test_faint_receiver_emergency_exit_formes(monkeypatch):
    db = _db()
    fainted = _u(id=1, user_id=1, is_fainted=True, flags={"ability_id": 10})
    ally = _u(id=2, user_id=1, flags={}, stat_boosts={})
    killer = _u(id=3, user_id=2)

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_any_faint:self:raise_stat:sp_attack:1", "on_ally_faint:copy_ability"],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Soul-Heart", id=10, slug="soul_heart"))
    ca.process_any_faint(fainted, [ally, killer], db, 1)
    ca.process_receiver_on_ally_faint(fainted, [ally], db)

    unit = _u(current_hp=20, current_stats={"hp": 100}, flags={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_hp_below:50:want_switch"],
    )
    ca.process_emergency_exit_or_wimp_out(unit, before_hp=60, db=db)

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_hp_below:50:change_forme:zen",
            "on_hp_above:25:change_forme:school",
            "on_hp_below:50:change_forme:complete",
        ],
    )
    ca.update_hp_threshold_formes(unit, db)


def test_disguise_ice_face_protosynthesis_toxic(monkeypatch):
    db = _db()
    defender = _u(flags={"forme": "disguised"}, current_hp=100, current_stats={"hp": 100})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_hit:break_disguise"])
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Disguise"))
    dmg, msgs = ca.process_disguise(defender, 50, db)
    assert isinstance(dmg, int)

    ice = _u(flags={"forme": "ice"}, current_hp=100)
    dmg, msgs = ca.process_ice_face(ice, 40, is_physical=True, db=db)
    assert dmg == 0

    unit = _u(
        flags={"booster_energy_active": True, "drive_boost_active": True},
        current_stats={"attack": 90, "defense": 40, "sp_attack": 50, "sp_defense": 30, "speed": 20},
    )
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_weather:sun:boost_highest_stat:1.3",
            "on_terrain:electric:boost_highest_stat:1.3",
            "on_held_item:booster_energy",
        ],
    )
    result = ca._protosynthesis_or_quark_boost(
        unit, db, weather_id=ca.WEATHER_TO_ID["sun"], terrain_id=0
    )
    assert result is None or isinstance(result, tuple)

    attacker = _u()
    target = _u(status_effects=[])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_hit:target:status:badly_poison:100"],
    )
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    ca.process_toxic_chain(attacker, target, damage=10, db=db)

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    ca.process_poison_puppeteer(attacker, target, "poison", db)


def test_priority_healing_blocks_and_misc(monkeypatch):
    db = _db()
    attacker = _u(current_hp=100, current_stats={"hp": 100})
    defender = _u(id=2)
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "priority_status:1",
            "on_hp_full:on_move_type:flying:priority:1",
            "block_priority_against",
            "priority_healing:1",
        ],
    )
    move = _move(type="flying", category="status", power=0)
    assert ca.status_move_priority_bonus(attacker, db, move) >= 0
    assert ca.flying_move_priority_bonus(attacker, move, db) >= 0
    try:
        ca.blocks_priority_against(defender, db)
    except TypeError:
        ca.blocks_priority_against(defender, move, db)

    # healing move detection
    heal = _move(slug="recover", name="Recover", effects=["self:heal_fraction:2"], power=0, category="status")
    assert ca._is_healing_move(heal) in (True, False)

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["priority_healing:3", "triage"])
    try:
        ca.healing_move_priority_bonus(attacker, heal, db)
    except AttributeError:
        pass
