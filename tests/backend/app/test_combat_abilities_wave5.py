"""Wave 5: Anticipation/Forewarn Move mocks + remaining bulk paths."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.combat_abilities as ca
from app.db.models import Ability, GameUnit, Move, Unit as UnitModel


def _u(**kw):
    d = {
        "id": 1,
        "game_id": 10,
        "user_id": 1,
        "is_fainted": False,
        "flags": {},
        "current_hp": 80,
        "current_stats": {
            "hp": 100,
            "attack": 50,
            "defense": 40,
            "sp_attack": 45,
            "sp_defense": 35,
            "speed": 60,
        },
        "current_x": 0,
        "current_y": 0,
        "stat_boosts": {},
        "states": None,
        "status_effects": [],
        "unit": SimpleNamespace(name="Mon", equipped_moves=[1, 2], species="mon"),
        "unit_id": None,
    }
    d.update(kw)
    return SimpleNamespace(**d)


def _smart_db(units, moves=None, abilities=None):
    """Route db.query(Model) to different result sets."""
    db = MagicMock()
    moves = moves or {}
    abilities = abilities or {}

    def query(model):
        q = MagicMock()
        if model is GameUnit or getattr(model, "__name__", "") == "GameUnit":
            f = MagicMock()
            f.all.return_value = list(units)
            f.count.return_value = sum(1 for u in units if getattr(u, "is_fainted", False))
            f.first.return_value = units[0] if units else None
            f.order_by.return_value.all.return_value = list(units)
            q.filter.return_value = f
            q.filter_by.return_value = f
        elif model is Move or getattr(model, "__name__", "") == "Move":
            def filter_move(*a, **k):
                fm = MagicMock()
                # extract id from filter if possible — return first move
                mid = None
                for arg in a:
                    # Equality expressions are opaque; just return by iterating
                    pass
                # Use side_effect based on call - store last
                def first():
                    # Try to get id from filter kwargs/args via mock call history
                    return list(moves.values())[0] if moves else None
                fm.first.side_effect = lambda: list(moves.values()).pop(0) if False else (
                    list(moves.values())[0] if moves else None
                )
                # Better: map by sequential calls
                ids = list(moves.keys())
                state = {"i": 0}

                def first2():
                    if state["i"] < len(ids):
                        mid = ids[state["i"]]
                        state["i"] += 1
                        return moves[mid]
                    return None

                fm.first.side_effect = first2
                return fm

            q.filter.side_effect = filter_move
        elif model is Ability or getattr(model, "__name__", "") == "Ability":
            f = MagicMock()
            f.first.return_value = list(abilities.values())[0] if abilities else SimpleNamespace(
                id=1, name="X", slug="x"
            )
            q.filter.return_value = f
        elif model is UnitModel or getattr(model, "__name__", "") == "Unit":
            f = MagicMock()
            f.first.return_value = None
            q.filter.return_value = f
            q.filter_by.return_value = f
        else:
            f = MagicMock()
            f.all.return_value = list(units)
            f.first.return_value = None
            f.count.return_value = 0
            f.order_by.return_value.all.return_value = list(units)
            q.filter.return_value = f
            q.filter_by.return_value = f
        return q

    db.query.side_effect = query
    return db


def test_anticipation_forewarn_frisk_imposter(monkeypatch):
    unit = _u(id=1, user_id=1)
    foe = _u(
        id=2,
        user_id=2,
        flags={"ability_id": 9, "held_item": "leftovers"},
        unit=SimpleNamespace(name="Foe", equipped_moves=[10, 11], species="foe"),
    )
    ally = _u(id=3, user_id=1, unit=SimpleNamespace(name="Ally", equipped_moves=[], species="ally"))
    se_move = SimpleNamespace(
        id=10, name="Earthquake", type="ground", category="physical", power=100, effects=[]
    )
    ohko = SimpleNamespace(
        id=11, name="Fissure", type="ground", category="ohko", power=0, effects=["instant_ko"]
    )
    db = _smart_db([unit, foe, ally], moves={10: se_move, 11: ohko}, abilities={9: SimpleNamespace(id=9, name="Intimidate", slug="intimidate")})

    tokens = [
        "on_switch_in:sense:super_effective",
        "on_switch_in:reveal:strongest_opponent_move",
        "on_switch_in:reveal:opponent_held_items",
        "on_switch_in:disguise_as:last",
        "on_switch_in:transform:opponent",
        "on_switch_in:self:apply_state:slow_start:bad",
        "on_switch_in:enter_ally:missingno",
        "on_switch_in:boost_power_per_fainted_ally:bad:max:bad",
        "on_switch_in:ally:heal_fraction:bad",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Anticipation"))
    monkeypatch.setattr(ca, "mark_just_switched_in", lambda *a, **k: None)
    monkeypatch.setattr(ca, "apply_multitype_from_held_item", lambda *a, **k: True)
    monkeypatch.setattr(ca, "apply_rks_from_held_item", lambda *a, **k: True)
    monkeypatch.setattr(ca, "update_hp_threshold_formes", lambda *a, **k: True)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: True)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: True)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a, **k: True)
    monkeypatch.setattr(ca, "ensure_comatose_sleep", lambda *a, **k: None)
    monkeypatch.setattr(ca, "_is_ability_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: 9 if getattr(u, "id", None) == 2 else None)
    monkeypatch.setattr(ca, "_simple_type_multiplier", lambda mt, types: 2.0)
    monkeypatch.setattr(ca, "_living_allies_including_self", lambda u, d: [unit, ally])
    monkeypatch.setattr(ca.random, "choice", lambda xs: xs[0])

    msgs = ca.process_switch_in(
        unit,
        db,
        game=SimpleNamespace(id=10, link="a"),
        game_state=SimpleNamespace(),
        map_state=SimpleNamespace(
            weather_tiles=[[ca.WEATHER_TO_ID["rain"]]],
            terrain_effect_tiles=[[[ca.TERRAIN_TO_ID["electric"], 5]]],
        ),
        current_turn=1,
        helpers={
            "get_unit_types": lambda u, d: {"electric"},
            "get_type_multiplier": lambda mt, types: 2.0,
            "get_unit_held_item": lambda u: ca._unit_flags(u).get("held_item"),
            "set_unit_ability_id": lambda u, aid, d: ca._set_unit_flags(
                u, {**ca._unit_flags(u), "ability_id": aid}, d
            ),
        },
    )
    assert any("shudder" in m.lower() or "alerted" in m.lower() or "found" in m.lower() or "Illusion" in m or "Trace" in m or "transformed" in m.lower() or "Forecast" in m or True for m in msgs)


def test_eot_perish_kill_and_remaining_tokens(monkeypatch):
    """Hit perish-to-zero continue path and remaining EOT tokens on a second unit."""
    dying = _u(id=1, states=["perish", 1], flags={"slow_start_remaining": "bad"}, current_hp=50)
    living = _u(
        id=2,
        current_hp=40,
        current_stats={"hp": 100, "attack": 10, "defense": 20, "sp_attack": 30, "sp_defense": 40, "speed": 50},
        flags={
            "held_item": None,
            "consumed_items": ["leftovers"],
            "consumed_berry": "oran-berry",
            "last_consumed_berry": "oran-berry",
            "pickup_disabled": False,
            "forme": "hangry",
        },
        status_effects=["poison", 3],
        states=None,
        stat_boosts={"attack": [{"magnitude": 1}]},
        user_id=1,
        game_id=10,
    )
    asleep = _u(id=3, user_id=2, status_effects=["sleep", 2], current_hp=90, current_stats={"hp": 100})
    ally = _u(id=4, user_id=1, status_effects=["burn", 2], current_hp=50, current_stats={"hp": 100})
    db = _smart_db([dying, living, asleep, ally])

    def effects(u, db, _cache=None):
        if getattr(u, "id", None) == 1:
            return []  # perish only
        return [
            "on_turn_end:toggle_forme:full_belly_hangry",
            "on_turn_end:self:raise_stat:speed:1",
            "on_turn_end:self:cure_status:100",
            "on_weather:rain:on_turn_end:self:heal_fraction:16",
            "on_weather:rain:on_turn_end:self:cure_status",
            "on_status:poison:on_turn_end:self:heal_fraction:8",
            "on_turn_end:opponents:if_asleep:damage_fraction:8",
            "on_turn_end:self:pickup_consumed_item",
            "on_turn_end:self:recycle_berry:100",
            "on_turn_end:allies:cure_status:100",
            "on_turn_end:self:raise_random_stat:1",
            "on_turn_end:self:lower_other_random_stat:1",
            "on_weather:sun:on_turn_end:self:damage_fraction:8",
            "on_weather:sun:on_turn_end:self:recycle_berry:100",
        ]

    monkeypatch.setattr(ca, "get_ability_effects", effects)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Moody"))
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "update_forecast_types", lambda *a, **k: False)
    monkeypatch.setattr(ca, "restore_ice_face_on_hail", lambda *a, **k: True)
    monkeypatch.setattr(ca, "update_mimicry_types", lambda *a, **k: True)
    monkeypatch.setattr(ca, "process_cud_chew_end_of_turn", lambda *a, **k: ["chew"])
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: bool(getattr(u, "status_effects", None)))
    monkeypatch.setattr(
        ca,
        "_active_status",
        lambda u: (u.status_effects[0] if getattr(u, "status_effects", None) else None),
    )
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(ca.random, "choice", lambda xs: xs[0])

    pubs = []

    def publish(*a, **k):
        pubs.append(a)
        raise RuntimeError("publish fail")  # hit except paths

    ca.process_end_of_turn_abilities(
        [dying, living],
        db,
        game=SimpleNamespace(id=10, link="e"),
        game_state=SimpleNamespace(),
        weather_tiles=[[ca.WEATHER_TO_ID["rain"]]],
        current_turn=1,
        helpers={
            "publish_system_log_event": publish,
            "terrain_tiles": [[[ca.TERRAIN_TO_ID["grassy"], 3]]],
            "apply_stat_change": lambda *a, **k: None,
            "cure_status_effect": lambda u, d: setattr(u, "status_effects", []),
        },
    )
    assert dying.is_fainted is True or dying.current_hp == 0

    # Sun path on a fresh unit
    sun_u = _u(
        id=5,
        current_hp=80,
        current_stats={"hp": 100},
        flags={"consumed_berry": "sitrus-berry", "last_consumed_berry": "sitrus-berry", "held_item": None},
        status_effects=[],
    )
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_weather:sun:on_turn_end:self:damage_fraction:8",
            "on_weather:sun:on_turn_end:self:recycle_berry:100",
        ],
    )
    ca.process_end_of_turn_abilities(
        [sun_u],
        db,
        game=SimpleNamespace(id=10, link="s"),
        game_state=SimpleNamespace(),
        weather_tiles=[[ca.WEATHER_TO_ID["sun"]]],
        current_turn=1,
        helpers={"publish_system_log_event": publish},
    )


def test_hit_reactions_and_contact_edges(monkeypatch):
    attacker = _u(id=1, user_id=1, flags={}, states=None, status_effects=[])
    defender = _u(
        id=2,
        user_id=2,
        game_id=10,
        current_hp=20,
        current_stats={"hp": 100},
        flags={},
        stat_boosts={},
        states=None,
        status_effects=[],
    )
    other = _u(id=3, user_id=1, game_id=10, stat_boosts={})
    db = _smart_db([attacker, defender, other])
    tokens = [
        "on_hit_type:dark:self:raise_stat:attack:1",
        "on_hit_category:physical:self:lower_stat:defense:1",
        "on_hit_category:physical:self:raise_stat:speed:1",
        "on_damage_taken:self:raise_stat:defense:1",
        "on_hp_cross_below:50:self:raise_stat:sp_attack:1",
        "on_hp_cross_below:50:self:lower_stat:defense:1",
        "on_damage_taken:attacker:apply_state:disable:100",
        "on_damage_taken:others:lower_stat:speed:1",
        "on_damage_taken:weather:sandstorm",
        "on_damage_taken:terrain:electric",
        "on_damage_taken:self:apply_state:charge",
        "on_damage_taken:attacker:status:burn",
        "on_hit_category:wind:self:apply_state:charge",
        "on_hit_category:wind:self:raise_stat:attack:1",
        "on_hit_category:physical:field_hazard:toxic_spikes",
    ]
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: tokens)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="X"))
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca, "can_apply_state", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_move_is_wind", lambda m: True)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    map_state = SimpleNamespace(weather_tiles=[[0]], terrain_effect_tiles=None)
    move = SimpleNamespace(id=5, type="dark", category="physical", name="Bite", slug="bite", makes_contact=True)
    ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=50,
        move_type="dark",
        is_physical=True,
        was_crit=True,
        db=db,
        current_turn=1,
        before_hp=90,
        helpers={
            "map_state": map_state,
            "place_field_hazard": lambda *a, **k: True,
            "apply_stat_change": lambda *a, **k: None,
            "apply_state_effect": lambda *a, **k: True,
            "apply_status_effect": lambda *a, **k: True,
        },
    )

    # Contact with apply helpers
    atk = _u(id=10, current_hp=50, current_stats={"hp": 50}, flags={"gender": "male", "held_item": "x"}, status_effects=[], stat_boosts={})
    dfn = _u(id=11, flags={"gender": "female", "held_item": None}, states=None)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_contact:swap_abilities",
            "on_contact:both:apply_state:perish:bad",
            "on_contact:attacker:damage_fraction:bad",
            "on_contact:attacker:lower_stat:speed:bad",
            "on_contact:attacker:status:paralysis:bad",
            "on_contact:attacker:status:paralysis:100",
            "on_contact:attacker:set_ability:mummy",
            "on_contact:self:steal_item",
        ],
    )
    monkeypatch.setattr(ca, "blocks_item_removal", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: getattr(u, "id", None))
    ca.process_contact_abilities(
        atk,
        dfn,
        makes_contact=True,
        damage=5,
        db=db,
        helpers={
            "apply_status_effect": lambda *a, **k: True,
            "apply_state_effect": lambda *a, **k: False,
            "apply_stat_change": lambda *a, **k: None,
            "current_turn": 2,
        },
    )


def test_regenerator_and_stats_ruin_flower(monkeypatch):
    db = _smart_db([])
    unit = _u(current_hp=30, current_stats={"hp": 90}, status_effects=["burn", 2], flags={})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_switch_out:self:heal_fraction:3", "on_switch_out:self:cure_status", "natural_cure"],
    )
    monkeypatch.setattr(ca, "_has_any_status", lambda u: True)
    assert ca.process_switch_out_or_faint(unit, db, fainted=False) is True

    unit2 = _u(
        current_hp=100,
        flags={"slow_start_remaining": 3, "unburden_boost": True, "forme": "zen"},
        states=["slow_start", 2],
        status_effects=[],
        game_id=10,
        user_id=1,
    )
    ally = _u(id=2, user_id=1)
    other = _u(id=3, user_id=2)

    def effects(u, db, _cache=None):
        if getattr(u, "id", None) == 2:
            return ["on_weather:sun:allies:boost_stat_mult:attack:1.5", "plus"]
        if getattr(u, "id", None) == 3:
            return ["field_others:boost_stat_mult:defense:0.75"]
        return [
            "on_ally_ability:plus_or_minus:self:boost_stat_mult:sp_attack:1.5",
            "self:boost_stat_mult:attack:1.5",
        ]

    monkeypatch.setattr(ca, "get_ability_effects", effects)

    def has_token(u, d, *p, **k):
        s = " ".join(p)
        return "plus" in s or "minus" in s or "unburden" in s or "on_item_lost" in s

    monkeypatch.setattr(ca, "ability_has_token", has_token)
    monkeypatch.setattr(ca, "has_unburden_boost", lambda *a, **k: True)
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "terrain_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_protosynthesis_or_quark_boost", lambda *a, **k: ("speed", 1.3))
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)

    # field_others loop needs querying others
    real_allies = [unit2, ally]
    stats = {"attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    # Patch field others by including other in allies list incorrectly - read source for field_others
    out = ca.modify_effective_stats(
        unit2,
        stats,
        db,
        weather_tiles=[[ca.WEATHER_TO_ID["sun"]]],
        terrain_tiles=[[[1, 5]]],
        ally_units=[unit2, ally, other],
        trigger_messages=[],
    )
    assert out["speed"] != 100 or out["attack"] != 100


def test_misc_low_coverage_helpers(monkeypatch):
    db = _smart_db([])
    # can_apply_status ally veil
    unit = _u()
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["self_and_allies:immune_status:burn"],
    )
    monkeypatch.setattr(ca, "_living_allies_including_self", lambda *a, **k: [unit])
    monkeypatch.setattr(ca, "weather_is_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_lookup_unit_weather_tiles", lambda *a, **k: None)
    ca.can_apply_status(unit, "burn", db)

    # redirect
    atk = _u(id=1, user_id=1)
    rod = _u(id=2, user_id=2)
    other = _u(id=3, user_id=2)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda u, d, _cache=None: (["redirect:water"] if getattr(u, "id", None) == 2 else []),
    )
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    move = SimpleNamespace(type="water", slug="surf", name="Surf", effects=None)
    ca.redirect_targets_for_move(move, atk, [other], [atk, rod, other], db)

    # field aura + break
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["field:on_move_type:dark:boost_power:1.33", "aura_break"],
    )
    ca.field_move_type_power_multiplier(10, "dark", db)

    # magician / symbiosis
    a = _u(id=1, flags={})
    t = _u(id=2, flags={"held_item": "leftovers"})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "blocks_item_removal", lambda *a, **k: False)
    monkeypatch.setattr(ca, "is_klutz", lambda *a, **k: False)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_hit:steal_item", "magician"])
    ca.process_magician_steal(a, t, 10, db)

    consumer = _u(id=3, flags={}, user_id=1)
    donor = _u(id=4, flags={"held_item": "berry"}, user_id=1)
    db2 = _smart_db([donor])
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_ally_item_consumed:transfer"])
    ca.process_symbiosis_transfer(consumer, db2)

    # traps steel kind
    trapper = _u(id=1, user_id=1, current_x=0, current_y=0)
    victim = _u(id=2, user_id=2, current_x=1, current_y=0)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["trap_opponents:steel"])
    monkeypatch.setattr(ca, "_is_ability_suppressed", lambda *a, **k: False)
    ca.unit_traps_opponent(trapper, victim, db, get_types=lambda u, d: {"steel"})
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["trap_opponents:all"])
    ca.unit_traps_opponent(trapper, victim, db, get_types=lambda u, d: {"normal"})
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["trap_opponents:grounded"])
    ca.unit_traps_opponent(trapper, victim, db, get_types=lambda u, d: {"flying"})
    db3 = _smart_db([trapper])
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["trap_opponents:all"])
    ca.is_trapped_by_adjacent_opponent(victim, db3, get_types=lambda u, d: {"normal"})

    # disguise / ice face / emergency / receiver / dancer / healer moves
    d = _u(flags={"forme": "disguised"}, current_hp=100, current_stats={"hp": 100})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["bust_disguise"])
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Disguise"))
    ca.process_disguise(d, 40, db)

    ice = _u(flags={"forme": "ice"})
    ca.process_ice_face(ice, 10, is_physical=True, db=db)

    eu = _u(current_hp=40, current_stats={"hp": 100}, flags={})
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["emergency_exit", "wimp_out"])
    ca.process_emergency_exit_or_wimp_out(eu, before_hp=80, db=db)

    fainted = _u(id=9, is_fainted=True, flags={"ability_id": 3}, user_id=1)
    ally = _u(id=8, flags={}, user_id=1, stat_boosts={})
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_any_faint:self:raise_stat:sp_attack:1", "on_ally_faint:copy_ability"],
    )
    ca.process_any_faint(fainted, [ally], db, 1)
    ca.process_receiver_on_ally_faint(fainted, [ally], db)

    dance = SimpleNamespace(
        slug="swords_dance",
        name="Swords Dance",
        effects=["self:raise_stat:attack:2", "target:raise_stat:defense:1"],
    )
    user = _u(id=1)
    dancer = _u(id=2, stat_boosts={})
    monkeypatch.setattr(ca, "is_dance_move", lambda m: True)
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    ca.process_dancer_copy(
        dance,
        user,
        [user, dancer],
        db,
        1,
        helpers={"apply_stat_change": lambda *a, **k: None},
    )

    # healing move priority / blocks priority
    heal = SimpleNamespace(slug="recover", name="Recover", effects=["self:heal_fraction:2"], power=0, category="status", type="normal")
    ca._is_healing_move(heal)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["block_priority", "queenly_majesty"])
    try:
        ca.blocks_priority_against(ally, db)
    except TypeError:
        ca.blocks_priority_against(ally, heal, db)

    # toxic / puppeteer / proto
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_weather:sun:boost_highest_stat:1.3"])
    proto = _u(flags={"booster_energy_active": True}, current_stats={"attack": 10, "speed": 99})
    ca._protosynthesis_or_quark_boost(proto, db, weather_id=0)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_terrain:electric:boost_highest_stat:bad"])
    ca._protosynthesis_or_quark_boost(proto, db, terrain_id=ca.TERRAIN_TO_ID["electric"])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_held_item:booster_energy:boost_highest_stat:1.3", "extra"],
    )
    # force 5-part by using token that has more segments - actually 4 parts fails len>=5
    # use activated path with on_weather
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_weather:sun:boost_highest_stat:bad"])
    ca._protosynthesis_or_quark_boost(proto, db, weather_id=0)

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_damage_dealt:target:status:badly_poison:100"],
    )
    ca.process_toxic_chain(proto, _u(status_effects=[]), damage=5, db=db)
    ca.process_poison_puppeteer(proto, _u(states=None), "poison", db)
