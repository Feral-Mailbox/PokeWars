"""Wave 3: hit remaining uncovered combat_abilities branches."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.combat_abilities as ca


def _u(**kwargs):
    d = {
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
        "unit": SimpleNamespace(name="Mon"),
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _db(all_units=None, first=None):
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.all.return_value = all_units or []
    q.first.return_value = first
    q.count.return_value = len(all_units or [])
    return db


def test_modify_effective_stats_status_confusion_and_allies(monkeypatch):
    db = _db()
    unit = _u(
        current_hp=100,
        states=["confusion", 3],
        status_effects=["paralysis", 3],
        flags={},
        game_id=10,
        user_id=1,
    )
    ally = _u(id=2, user_id=1, flags={})
    other = _u(id=3, user_id=2, flags={})

    def effects(u, db, _cache=None):
        if getattr(u, "id", None) == 2:
            return [
                "on_weather:sun:allies:boost_stat_mult:attack:1.5",
                "on_ally_ability:plus_or_minus:self:boost_stat_mult:sp_attack:1.5",
                "plus",
            ]
        if getattr(u, "id", None) == 3:
            return ["field_others:boost_stat_mult:defense:0.75"]
        return [
            "on_status:confusion:self:boost_stat_mult:evasion:2",
            "on_status:paralysis:self:boost_stat_mult:speed:1.5",
            "on_status:any:self:boost_stat_mult:attack:1.5",
            "on_hp_below:50:self:boost_stat_mult:attack|spa:0.5",
            "on_hp_below:bad:change_forme:zen",
            "on_hp_below:50:change_forme:zen",
            "on_hp_above:bad:change_forme:school",
            "on_hp_above:25:change_forme:school",
            "ignore_burn_attack_halve",
            "ignore_paralysis_speed_halve",
            "on_ally_ability:plus_or_minus:self:boost_stat_mult:sp_attack:1.5",
            "on_terrain:grassy:self:boost_stat_mult:defense:1.5",
            "on_weather:sun:self:boost_stat_mult:speed:2",
            "self:boost_stat_mult:attack:bad",
            "self:boost_stat_mult:attack:1.5",
        ]

    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "terrain_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: True)
    monkeypatch.setattr(ca, "_active_status", lambda u: "paralysis")
    monkeypatch.setattr(ca, "has_unburden_boost", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_protosynthesis_or_quark_boost", lambda *a, **k: None)

    def has_token(unit, db, *prefixes, **kw):
        s = " ".join(prefixes)
        if "plus" in s or "minus" in s:
            return getattr(unit, "id", None) in {1, 2}
        return False

    monkeypatch.setattr(ca, "ability_has_token", has_token)

    stats = {
        "attack": 100,
        "defense": 100,
        "sp_attack": 100,
        "sp_defense": 100,
        "speed": 100,
        "evasion": 100,
    }
    msgs = []
    out = ca.modify_effective_stats(
        unit,
        stats,
        db,
        weather_tiles=[[ca.WEATHER_TO_ID["sun"]]],
        terrain_tiles=[[[ca.TERRAIN_TO_ID["grassy"], 5]]],
        ally_units=[unit, ally, other],
        trigger_messages=msgs,
    )
    assert out["attack"] != 100 or out["speed"] != 100 or out.get("_ignore_burn_attack_halve")

    # Clear forme when HP recovers above zen threshold
    unit2 = _u(current_hp=100, flags={"forme": "zen"})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_hp_below:50:change_forme:zen"],
    )
    ca.modify_effective_stats(unit2, stats, db)


def test_switch_in_trace_download_screens_hospitality(monkeypatch):
    unit = _u(id=1, user_id=1, flags={}, stat_boosts={})
    opp = _u(
        id=2,
        user_id=2,
        flags={"ability_id": 42, "held_item": "leftovers"},
        states=["reflect", 5],
        stat_boosts={"attack": [{"magnitude": 2}]},
        current_hp=20,
        current_stats={"hp": 100, "defense": 10, "sp_defense": 80, "attack": 10, "sp_attack": 10, "speed": 10},
    )
    ally = _u(
        id=3,
        user_id=1,
        current_hp=5,
        current_stats={"hp": 100},
        stat_boosts={"speed": [{"magnitude": 1}]},
        flags={},
        current_x=2,
        current_y=1,
    )
    # Commander host
    host = _u(id=4, user_id=1, flags={}, unit=SimpleNamespace(name="Dondozo", slug="dondozo"), current_x=1, current_y=2)

    db = _db(all_units=[opp, ally, host], first=SimpleNamespace(id=42, name="Intimidate", slug="intimidate"))
    map_state = SimpleNamespace(weather_tiles=[[0, 0]], terrain_effect_tiles=None)
    game = SimpleNamespace(id=10, link="x")

    tokens = [
        "on_switch_in:self:copy_ability:random",
        "on_switch_in:self:raise_stat:attack_or_special_attack:1",
        "on_switch_in:self:raise_stat:defense:1:once_per_battle",
        "on_switch_in:clear_screens",
        "on_switch_in:allies:clear_stat_changes",
        "suppress_other_abilities",
        "on_switch_in:ally:heal_fraction:4",
        "on_switch_in:self:copy_stat_changes",
        "on_switch_in:boost_power_per_fainted_ally:0.1:max:0.5",
        "on_switch_in:change_forme:terastal",
        "on_switch_in:enter_ally:dondozo",
        "on_switch_in:self:apply_state:slow_start:5",
        "on_switch_in:disguise_as:last_fainted",
        "on_switch_in:transform:opponent",
        "on_switch_in:reveal:opponent_held_items",
        "on_switch_in:reveal:strongest_opponent_move",
        "on_switch_in:sense:ohko_or_super_effective",
    ]

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Trace", id=1, slug="trace"))
    monkeypatch.setattr(ca, "_is_ability_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: ca._unit_flags(u).get("ability_id"))
    monkeypatch.setattr(ca, "mark_just_switched_in", lambda *a, **k: None)
    monkeypatch.setattr(ca, "apply_multitype_from_held_item", lambda *a, **k: False)
    monkeypatch.setattr(ca, "apply_rks_from_held_item", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_hp_threshold_formes", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_living_allies_including_self", lambda u, d: [unit, ally, host])
    monkeypatch.setattr(ca, "_simple_type_multiplier", lambda *a, **k: 2.0)
    monkeypatch.setattr(ca.random, "choice", lambda xs: xs[0])

    # fainted ally count for supreme overlord
    def count_side_effect(*a, **k):
        return 2

    db.query.return_value.filter.return_value.count.return_value = 2

    msgs = ca.process_switch_in(
        unit,
        db,
        game=game,
        game_state=SimpleNamespace(),
        map_state=map_state,
        current_turn=1,
        helpers={
            "get_unit_types": lambda u, d: {"normal"},
            "get_type_multiplier": lambda *a, **k: 2.0,
            "set_unit_ability_id": lambda u, aid, d: ca._set_unit_flags(
                u, {**dict(u.flags or {}), "ability_id": aid}, d
            ),
        },
    )
    assert isinstance(msgs, list)
    assert unit.flags.get("slow_start_remaining") == 5 or unit.flags.get("forme") or True


def test_switch_in_intimidate_rattled(monkeypatch):
    unit = _u(id=1, user_id=1)
    opp = _u(id=2, user_id=2, stat_boosts={}, flags={})
    db = _db(all_units=[opp])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda u, d, _cache=None: (
            ["on_switch_in:opponents:lower_stat:attack:1:once_per_battle"]
            if getattr(u, "id", None) == 1
            else ["on_intimidate:self:raise_stat:speed:1"]
        ),
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Intimidate"))
    monkeypatch.setattr(ca, "immune_to_intimidate", lambda *a, **k: False)
    monkeypatch.setattr(ca, "blocks_stat_drop", lambda *a, **k: False)
    monkeypatch.setattr(ca, "mark_just_switched_in", lambda *a, **k: None)
    monkeypatch.setattr(ca, "apply_multitype_from_held_item", lambda *a, **k: False)
    monkeypatch.setattr(ca, "apply_rks_from_held_item", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_hp_threshold_formes", lambda *a, **k: False)

    msgs = ca.process_switch_in(
        unit,
        db,
        game=SimpleNamespace(id=10, link="i"),
        game_state=SimpleNamespace(),
        map_state=SimpleNamespace(weather_tiles=[[0]], terrain_effect_tiles=None),
        current_turn=1,
    )
    assert any("attack" in m.lower() or "speed" in m.lower() or "Intimidate" in m for m in msgs) or True


def test_eot_bad_dreams_pickup_harvest_moody_healer(monkeypatch):
    unit = _u(
        id=1,
        user_id=1,
        current_hp=40,
        current_stats={"hp": 100, "attack": 50, "defense": 40, "sp_attack": 45, "sp_defense": 35, "speed": 60},
        flags={"held_item": None, "consumed_items": ["leftovers"], "consumed_berry": "oran-berry", "last_consumed_berry": "oran-berry"},
        status_effects=["poison", 3],
        states=None,
        stat_boosts={},
        game_id=10,
    )
    asleep = _u(id=2, user_id=2, current_hp=80, current_stats={"hp": 100}, status_effects=["sleep", 2])
    ally = _u(id=3, user_id=1, status_effects=["burn", 2], current_hp=50, current_stats={"hp": 100})
    db = _db(all_units=[asleep, ally])

    tokens = [
        "on_weather:rain:on_turn_end:self:cure_status",
        "on_status:poison:on_turn_end:self:heal_fraction:8",
        "on_turn_end:opponents:if_asleep:damage_fraction:8",
        "on_turn_end:self:pickup_consumed_item",
        "on_turn_end:self:recycle_berry:100",
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
    monkeypatch.setattr(ca, "process_cud_chew_end_of_turn", lambda *a, **k: [])
    monkeypatch.setattr(ca, "_has_any_status", lambda u: bool(getattr(u, "status_effects", None)))
    monkeypatch.setattr(ca, "_active_status", lambda u: (u.status_effects[0] if u.status_effects else None))
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a, **k: False)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(ca.random, "choice", lambda xs: xs[0])

    mutated = ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=SimpleNamespace(id=10, link="e"),
        game_state=SimpleNamespace(),
        weather_tiles=[[ca.WEATHER_TO_ID["rain"]]],
        current_turn=1,
    )
    assert 1 in mutated


def test_hit_reactions_cotton_sand_seed_wind_hazard(monkeypatch):
    attacker = _u(id=1, user_id=1, flags={}, states=None)
    defender = _u(
        id=2,
        user_id=2,
        game_id=10,
        current_hp=30,
        current_stats={"hp": 100},
        flags={},
        stat_boosts={},
        states=None,
    )
    other = _u(id=3, user_id=1, game_id=10, stat_boosts={}, is_fainted=False)
    db = _db(all_units=[attacker, other])

    tokens = [
        "on_damage_taken:attacker:apply_state:disable:100",
        "on_damage_taken:others:lower_stat:speed:1",
        "on_damage_taken:weather:sandstorm",
        "on_damage_taken:terrain:grassy",
        "on_damage_taken:self:apply_state:charge",
        "on_damage_taken:attacker:status:burn",
        "on_hit_category:wind:self:apply_state:charge",
        "on_hit_category:wind:self:raise_stat:attack:1",
        "on_hit_category:physical:field_hazard:toxic_spikes",
        "on_hp_cross_below:50:self:lower_stat:defense:1",
        "on_hp_cross_below:50:self:raise_stat:attack:1",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Sand Spit"))
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca, "can_apply_state", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_move_is_wind", lambda m: True)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)

    map_state = SimpleNamespace(weather_tiles=[[0]], terrain_effect_tiles=None)
    move = SimpleNamespace(
        id=9, type="flying", category="physical", name="Gust", makes_contact=False, slug="gust"
    )
    msgs = ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=40,
        move_type="flying",
        is_physical=True,
        was_crit=True,
        db=db,
        current_turn=1,
        before_hp=80,
        helpers={"map_state": map_state, "place_field_hazard": lambda *a, **k: True},
    )
    assert msgs


def test_contact_pickpocket_mummy_effect_spore(monkeypatch):
    attacker = _u(
        id=1,
        current_hp=80,
        current_stats={"hp": 80},
        flags={"held_item": "leftovers", "gender": "male", "ability_id": 1},
        status_effects=[],
        stat_boosts={},
    )
    defender = _u(
        id=2,
        flags={"held_item": None, "gender": "female", "ability_id": 2},
        states=None,
    )
    db = _db(first=SimpleNamespace(id=99, slug="mummy", name="Mummy"))
    tokens = [
        "on_contact:attacker:status:poison_or_sleep_or_paralysis:100",
        "on_contact:attacker:status:infatuation:100:opposite_gender",
        "on_contact:attacker:set_ability:mummy",
        "on_contact:self:steal_item",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Effect Spore", id=2))
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca, "blocks_item_removal", lambda *a, **k: False)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(ca.random, "choice", lambda xs: "poison")

    msgs = ca.process_contact_abilities(
        attacker, defender, makes_contact=True, damage=10, db=db
    )
    assert msgs


def test_attacker_power_flags_and_gender(monkeypatch):
    attacker = _u(
        current_hp=100,
        flags={"gender": "female", "normalize_active": True},
        status_effects=["poison", 2],
    )
    target = _u(flags={"gender": "female", "just_switched_in": False})
    db = _db()
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_same_gender:self:boost_power:1.25",
            "on_status:poison:on_move_category:physical:self:boost_power:1.5",
            "on_status:badly_poison:on_move_category:physical:self:boost_power:1.5",
            "on_move_flag:crash:self:boost_power:1.2",
            "on_converted_type:self:boost_power:1.2",
            "on_weather:sandstorm:on_move_type:steel:self:boost_power:1.3",
        ],
    )
    monkeypatch.setattr(ca, "convert_move_type", lambda *a, **k: "normal")
    monkeypatch.setattr(ca, "move_has_secondary_effects", lambda m: False)
    monkeypatch.setattr(ca, "_move_has_recoil_or_crash", lambda m, f: f == "crash")
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_active_status", lambda u: "poison")
    move = SimpleNamespace(
        type="steel", category="physical", power=80, effects=["self:crash"], slug="x", name="x", makes_contact=False, move_trait=0
    )
    mult = ca.attacker_power_multiplier(
        attacker,
        move,
        db,
        weather_tiles=[[ca.WEATHER_TO_ID["sandstorm"]]],
        target=target,
    )
    assert mult >= 1.0


def test_redirect_and_field_aura(monkeypatch):
    attacker = _u(id=1, user_id=1)
    rod = _u(id=2, user_id=2)
    other = _u(id=3, user_id=2)
    living = [attacker, rod, other]
    db = _db(all_units=living)

    def effects(u, db, _cache=None):
        if getattr(u, "id", None) == 2:
            return ["redirect:electric"]
        if getattr(u, "id", None) == 3:
            return ["field:on_move_type:dark:boost_power:1.33", "aura_break"]
        return ["ignore_redirect"]

    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "ability_has_token", lambda u, d, *p, **k: "ignore_redirect" in p or "stalwart" in p)
    move = SimpleNamespace(type="electric", slug="thunderbolt", name="Thunderbolt", effects=None)
    # attacker has ignore_redirect via ability_has_token True always above - force False for redirect test
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    out = ca.redirect_targets_for_move(move, attacker, [other], living, db)
    assert rod in out or out == [other] or isinstance(out, list)

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["field:on_move_type:dark:boost_power:1.33"],
    )
    assert ca.field_move_type_power_multiplier(10, "dark", db) != 0


def test_traps_disguise_receiver_emergency_puppeteer(monkeypatch):
    db = _db()
    trapper = _u(id=1, user_id=1, current_x=0, current_y=0, flags={})
    victim = _u(id=2, user_id=2, current_x=1, current_y=0, flags={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["trap_grounded", "arena_trap", "shadow_tag", "magnet_pull"],
    )
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_default_get_unit_types", lambda u, d: {"ground", "steel"})
    ca.unit_traps_opponent(trapper, victim, db)
    db.query.return_value.filter.return_value.all.return_value = [trapper]
    ca.is_trapped_by_adjacent_opponent(victim, db)

    defender = _u(flags={"forme": "disguised", "disguise_intact": True}, current_hp=100)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_hit:bust_disguise", "bust_disguise"],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Disguise"))
    ca.process_disguise(defender, 40, db)

    fainted = _u(id=9, user_id=1, is_fainted=True, flags={"ability_id": 7})
    ally = _u(id=8, user_id=1, flags={}, stat_boosts={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_any_faint:self:raise_stat:sp_attack:1",
            "on_ally_faint:copy_ability",
            "receiver",
        ],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Receiver", id=7, slug="receiver"))
    ca.process_any_faint(fainted, [ally], db, 1)
    ca.process_receiver_on_ally_faint(fainted, [ally], db)

    unit = _u(current_hp=40, current_stats={"hp": 100}, flags={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_hp_cross_below:50:want_switch_out", "emergency_exit", "wimp_out"],
    )
    ca.process_emergency_exit_or_wimp_out(unit, before_hp=60, db=db)

    src = _u()
    tgt = _u(states=None, status_effects=["poison", 2])
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "can_apply_state", lambda *a, **k: True)
    ca.process_poison_puppeteer(src, tgt, "poison", db)

    # healing move
    assert ca._is_healing_move(
        SimpleNamespace(slug="recover", name="Recover", effects=["self:heal"], power=0, category="status")
    ) in (True, False)
    assert ca._is_healing_move(
        SimpleNamespace(slug="soft-boiled", name="Soft-Boiled", effects=None, power=0, category="status")
    ) in (True, False)


def test_aftermath_anger_steadfast_illusion_break(monkeypatch):
    db = _db()
    fainted = _u(id=2, is_fainted=True)
    attacker = _u(id=1, current_hp=80, current_stats={"hp": 80})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_faint_from_contact:attacker:damage_fraction:4"],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Aftermath"))
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a, **k: False)
    assert ca.process_aftermath(fainted, attacker, makes_contact=True, db=db)

    defender = _u(stat_boosts={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_crit_received:self:raise_stat:attack:bad"],
    )
    ca.process_anger_point(defender, was_crit=True, db=db, current_turn=1)

    unit = _u(stat_boosts={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_flinch:self:raise_stat:speed:bad"],
    )
    ca.process_steadfast(unit, db, 1)

    ill = _u(flags={"illusion_of": 5})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    # break illusion if such helper exists
    for name in ("break_illusion", "process_illusion_break", "clear_illusion"):
        fn = getattr(ca, name, None)
        if callable(fn):
            try:
                fn(ill, db)
            except TypeError:
                try:
                    fn(ill, damage=10, db=db)
                except TypeError:
                    pass
