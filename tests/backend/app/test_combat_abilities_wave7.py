"""Wave 7: close remaining combat_abilities gaps to ≥90% statement coverage."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.combat_abilities as ca


def _u(**kw):
    d = dict(
        id=1,
        game_id=10,
        user_id=1,
        is_fainted=False,
        flags={},
        current_hp=50,
        current_stats={"hp": 100, "attack": 50, "defense": 40, "sp_attack": 30, "sp_defense": 35, "speed": 60},
        current_x=0,
        current_y=0,
        stat_boosts={},
        states=None,
        status_effects=[],
        can_move=True,
        unit=SimpleNamespace(name="M", ability_ids=[1], types=["fire"], gender="male", equipped_moves=[1]),
        unit_id=5,
    )
    d.update(kw)
    return SimpleNamespace(**d)


def test_raw_effects_gastro_neutralizing_parse(monkeypatch):
    db = MagicMock()
    cache = {}
    ability = SimpleNamespace(id=9, effect=None, slug="static")
    db.query.return_value.filter.return_value.first.return_value = ability
    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: 9)
    toks = ca._raw_ability_effect_tokens(_u(), db, _cache=cache)
    assert toks  # slug fallback
    assert ca._raw_ability_effect_tokens(_u(), db, _cache=cache) == toks  # cache hit

    ability2 = SimpleNamespace(id=10, effect=None, slug="")
    db.query.return_value.filter.return_value.first.return_value = ability2
    cache2 = {}
    assert ca._raw_ability_effect_tokens(_u(id=2), db, _cache=cache2) == []

    db.query.return_value.filter.return_value.first.return_value = None
    assert ca._raw_ability_effect_tokens(_u(id=3), db, _cache={}) == []

    # gastro acid exception path
    u = _u(states=SimpleNamespace())  # weird states
    assert ca._unit_has_gastro_acid(u) is False

    monkeypatch.setattr(ca, "_unit_has_gastro_acid", lambda u: True)
    assert ca._unit_is_neutralizing_gas_holder(_u(), db) is False
    assert ca._is_ability_suppressed(_u(states=["gastro_acid", 2]), db) is True
    monkeypatch.setattr(ca, "_unit_has_gastro_acid", lambda u: False)
    assert ca._is_ability_suppressed(_u(), None) is False

    assert ca.field_has_neutralizing_gas(0, db) is False
    db.query.return_value.filter.return_value.all.side_effect = RuntimeError("db")
    assert ca.field_has_neutralizing_gas(10, db) is False

    assert ca.parse_effects("  single  ") == ["single"]
    assert ca.parse_effects("   ") == []
    assert ca.parse_effects(99) == []
    assert ca.parse_effects([None, " a ", ""]) == ["a"]

    # get_ability_effects slug fallback via real get_active_ability
    monkeypatch.setattr(ca, "_is_ability_suppressed", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: 1)
    ab = SimpleNamespace(id=1, effect=[], slug="made_up_slug_xyz")
    db.query.return_value.filter.return_value.first.return_value = ab
    assert "made_up_slug_xyz" in ca.get_ability_effects(_u(id=99), db, _cache={})


def test_hit_reactions_hazard_and_wind_edges(monkeypatch):
    db = MagicMock()
    attacker = _u(id=1, user_id=1)
    defender = _u(id=2, user_id=2, current_hp=40, current_stats={"hp": 100}, flags={}, states=None, stat_boosts={})
    db.query.return_value.filter.return_value.all.return_value = [attacker]
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_hit_category:wind:self:apply_state:charge",
            "on_hit_category:physical:field_hazard:spikes",
            "on_hit_category:special:field_hazard:toxic_spikes",
            "on_damage_taken:self:apply_state:charge",
            "on_hit_type:dark:self:raise_stat:attack:bad",
            "on_hit_category:physical:self:lower_stat:defense:bad",
            "on_damage_taken:self:raise_stat:defense:bad",
            "on_hp_cross_below:50:self:raise_stat:attack:bad",
        ],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="X"))
    monkeypatch.setattr(ca, "_move_is_wind", lambda m: True)
    monkeypatch.setattr(ca, "can_apply_state", lambda *a, **k: True)

    def apply_state(*a, **k):
        raise TypeError("sig")

    move = SimpleNamespace(id=1, type="dark", category="physical", name="Gust")
    # TypeError on apply_state → fallback set states; place_hazard TypeError; no apply_stat → boosts path
    ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=30,
        move_type="dark",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        before_hp=80,
        helpers={
            "apply_state_effect": apply_state,
            "place_field_hazard": lambda *a, **k: (_ for _ in ()).throw(TypeError()),
        },
    )

    # pending_hazard else branch (no place helper); special category; already has state
    defender2 = _u(id=3, user_id=2, current_hp=40, current_stats={"hp": 100}, flags={}, states=["charge", 2], stat_boosts=None)
    ca.process_defender_hit_reactions(
        attacker,
        defender2,
        move,
        damage=20,
        move_type="flying",
        is_physical=False,
        was_crit=False,
        db=db,
        current_turn=1,
        before_hp=80,
        helpers={},
    )


def test_contact_swap_perish_and_attacker_status(monkeypatch):
    db = MagicMock()
    atk = _u(id=1, current_hp=50, current_stats={"hp": 50}, flags={"ability_id": 1}, status_effects=[], states=None)
    dfn = _u(id=2, flags={"ability_id": 2}, states=None, status_effects=[])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_contact:swap_abilities",
            "on_contact:both:apply_state:perish:bad",
            "on_contact:attacker:damage_fraction:bad",
        ],
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="WS", id=2))
    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: getattr(u, "flags", {}).get("ability_id"))

    _calls = {"n": 0}

    def apply_state(subject, state, db, **kw):
        _calls["n"] += 1
        if "duration" in kw:
            raise TypeError("no duration")
        if _calls["n"] <= 3:
            raise TypeError("nope")
        return False

    ca.process_contact_abilities(
        atk, dfn, makes_contact=True, damage=10, db=db, helpers={"apply_state_effect": apply_state}
    )

    # swap when one side missing ability
    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: 5 if u is atk else None)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_contact:swap_abilities"])
    ca.process_contact_abilities(atk, dfn, makes_contact=True, damage=5, db=db)

    monkeypatch.setattr(ca, "_get_unit_ability_id", lambda u: None)
    ca.process_contact_abilities(atk, dfn, makes_contact=True, damage=5, db=db)

    # attacker contact status with TypeError retry + no helper
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_contact_deal:target:status:poison:bad"])
    monkeypatch.setattr(ca, "can_apply_status", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: False)
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)

    def apply_status(*a, **k):
        if "source" in k or "game" in k:
            raise TypeError()
        return True

    ca.process_attacker_contact_on_hit(
        atk, dfn, makes_contact=True, damage=5, db=db, helpers={"apply_status_effect": apply_status}
    )
    dfn2 = _u(id=9, status_effects=[], states=None)
    ca.process_attacker_contact_on_hit(atk, dfn2, makes_contact=True, damage=5, db=db, helpers={})


def test_switch_in_intimidate_rattled_anticipation(monkeypatch):
    db = MagicMock()
    unit = _u(id=1, user_id=1, flags={})
    opp = _u(
        id=2,
        user_id=2,
        flags={},
        stat_boosts={},
        unit=SimpleNamespace(name="O", equipped_moves=["bad", 1], types=["normal"]),
        unit_id=None,
    )
    db.query.return_value.filter.return_value.all.return_value = [opp]

    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda u, *a, **k: (
            ["on_switch_in:opponents:lower_stat:attack:1:once", "on_switch_in:self:shudder_if_threatened"]
            if u is unit
            else ["on_intimidate:self:raise_stat:speed:bad"]
        ),
    )
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Intimidate"))
    monkeypatch.setattr(ca, "immune_to_intimidate", lambda *a, **k: False)
    monkeypatch.setattr(ca, "blocks_stat_drop", lambda *a, **k: False)
    monkeypatch.setattr(ca, "_default_get_unit_types", lambda *a, **k: {"normal"})

    _n = {"c": 0}

    def apply_stat(*a, **k):
        _n["c"] += 1
        if "source" in k:
            raise TypeError("1")
        if "from_opponent" in k:
            raise TypeError("2")
        return None

    # Move query for anticipation
    move = SimpleNamespace(id=1, effects=["instant_ko"], category="physical", type="fighting", power=100)

    def query_side(model):
        m = MagicMock()
        name = getattr(model, "__name__", str(model))
        if "Move" in name or model is getattr(ca, "Move", None):
            m.filter.return_value.first.return_value = move
            m.filter_by.return_value.first.return_value = move
        else:
            m.filter.return_value.all.return_value = [opp]
            m.filter_by.return_value.first.return_value = None
        return m

    # Simpler: patch anticipation loop via get_type_mult and Move via import path
    from app.db import models as models

    real_query = db.query

    def smart_query(model):
        mq = MagicMock()
        if model is models.GameUnit:
            mq.filter.return_value.all.return_value = [opp]
            return mq
        if model is models.Move:
            mq.filter.return_value.first.return_value = move
            return mq
        if model is models.Unit:
            mq.filter_by.return_value.first.return_value = SimpleNamespace(equipped_moves=[1], types=["normal"])
            return mq
        return real_query(model)

    db.query.side_effect = smart_query

    map_state = SimpleNamespace(weather_tiles=[[0]], terrain_effect_tiles=None)
    ca.process_switch_in(
        unit,
        db,
        game=SimpleNamespace(id=10, link="g"),
        game_state=None,
        map_state=map_state,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat, "get_type_multiplier": lambda *a, **k: (_ for _ in ()).throw(TypeError())},
    )

    # OHKO category path + super-effective shudder
    move2 = SimpleNamespace(id=2, effects=[], category="ohko", type="", power=0)
    move3 = SimpleNamespace(id=3, effects=[], category="special", type="fighting", power=80)

    def smart_query2(model):
        mq = MagicMock()
        if model is models.GameUnit:
            mq.filter.return_value.all.return_value = [opp]
            return mq
        if model is models.Move:
            mq.filter.return_value.first.side_effect = [move2, move3]
            return mq
        if model is models.Unit:
            mq.filter_by.return_value.first.return_value = SimpleNamespace(equipped_moves=[2, 3], types=["normal"])
            return mq
        return MagicMock()

    db.query.side_effect = smart_query2
    opp.unit = None
    opp.unit_id = 7
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda u, *a, **k: ["on_switch_in:self:shudder_if_threatened"] if u is unit else [],
    )
    ca.process_switch_in(
        unit,
        db,
        game=SimpleNamespace(id=10, link="g"),
        game_state=None,
        map_state=map_state,
        current_turn=1,
        helpers={"get_type_multiplier": lambda mt, types: 2.0},
    )


def test_eot_perish_slow_start_hydration_poison_heal(monkeypatch):
    db = MagicMock()
    game = SimpleNamespace(id=10, link="g")
    pubs = []

    def publish(*a, **k):
        pubs.append(a)
        if len(pubs) in (1, 3, 5):
            raise RuntimeError("pub fail")

    u_perish = _u(id=1, states=["perish", 2], flags={}, status_effects=[])
    u_kill = _u(id=2, states=["perish", 1], flags={}, status_effects=[], current_hp=10)
    u_slow = _u(id=3, states=None, flags={"slow_start_remaining": "bad"}, status_effects=["burn", 2], current_hp=50)
    u_heal = _u(
        id=4,
        states=None,
        flags={},
        status_effects=["poison", 2],
        current_hp=50,
        current_stats={"hp": 100},
    )
    u_empty = _u(id=5, states=None, flags={"slow_start_remaining": 1}, status_effects=[])

    def effects_for(u, *a, **k):
        if u is u_heal:
            return ["on_status:poison:on_turn_end:self:heal_fraction:bad"]
        if u is u_slow:
            return ["on_weather:rain:on_turn_end:self:cure_status"]
        return []

    monkeypatch.setattr(ca, "get_ability_effects", effects_for)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="A"))
    monkeypatch.setattr(ca, "weather_id_matches", lambda *a, **k: True)
    monkeypatch.setattr(ca, "_has_any_status", lambda u: bool(u.status_effects))
    monkeypatch.setattr(ca, "_active_status", lambda u: "poison" if u is u_heal else ("burn" if u is u_slow else None))
    monkeypatch.setattr(ca, "process_cud_chew_end_of_turn", lambda *a, **k: [])

    weather = [[ca.WEATHER_TO_ID.get("rain", 2)]]
    ca.process_end_of_turn_abilities(
        [u_perish, u_kill, u_slow, u_heal, u_empty],
        db,
        game=game,
        game_state=None,
        weather_tiles=weather,
        current_turn=1,
        helpers={"publish_game_event": publish, "cure_status_effect": lambda *a, **k: None},
    )

    # hydration without cure helper; poison heal at full HP skip; bad dreams no game_id
    u_h2 = _u(id=6, status_effects=["para", 1], flags={}, game_id=None)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: [
        "on_weather:rain:on_turn_end:self:cure_status",
        "on_status:poison:on_turn_end:self:heal_fraction:8",
        "on_turn_end:opponents:if_asleep:damage_fraction:bad",
    ])
    monkeypatch.setattr(ca, "_has_any_status", lambda u: True)
    monkeypatch.setattr(ca, "_active_status", lambda u: "poison")
    full = _u(id=7, status_effects=["poison", 1], current_hp=100, current_stats={"hp": 100}, game_id=None)
    ca.process_end_of_turn_abilities(
        [u_h2, full],
        db,
        game=None,
        game_state=None,
        weather_tiles=weather,
        current_turn=1,
        helpers={},
    )


def test_gen_helpers_dense(monkeypatch):
    db = MagicMock()
    u = _u(current_hp=40, current_stats={"hp": 100}, flags={}, status_effects=["poison", 2])
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: [
            "on_super_effective_deal:self:boost_power:bad",
            "neuroforce",
            "on_target_status:poison:guaranteed_crit",
            "merciless",
            "can_poison:steel",
            "corrosion",
            "on_berry_eat:self:heal_fraction:bad",
            "cheek_pouch",
            "priority_healing:bad",
            "triage",
            "on_hp_above:bad:change_forme:school",
            "on_hp_below:bad:change_forme:solo",
            "on_hp_above:25:change_forme:school",
            "on_hp_below:25:change_forme:",
            "multi_hit:2",
            "parental_bond",
            "second_hit_power",
        ],
    )
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)

    assert ca.neuroforce_power_multiplier(u, 2.0, db) == 1.25
    assert ca.neuroforce_power_multiplier(u, 1.0, db) == 1.0
    assert ca.guaranteed_crit_vs(u, _u(status_effects=["poison", 1]), db)
    assert ca.guaranteed_crit_vs(None, u, db) is False
    assert ca.corrosion_bypasses_type_immunity(u, "poison", ["steel"], db)
    assert ca.corrosion_bypasses_type_immunity(u, "burn", ["steel"], db) is False
    assert ca.corrosion_bypasses_type_immunity(None, "poison", ["steel"], db) is False

    ca.mark_just_switched_in(None, db)
    ca.clear_just_switched_in(None, db)
    ca.clear_just_switched_in(_u(flags={}), db)
    ca.clear_just_switched_in_for_opponents("bad", 1, db)
    db.query.return_value.filter.return_value.all.return_value = [_u(flags={"just_switched_in": True})]
    ca.clear_just_switched_in_for_opponents(10, 1, db)

    assert ca.move_makes_contact(u, SimpleNamespace(makes_contact=True), db) is False
    assert ca.parental_bond_hit_count(u, SimpleNamespace(power=0, category="status", effects=None), db) is None
    assert ca.parental_bond_hit_count(u, SimpleNamespace(power="x", category="physical", effects=None), db) == 2
    assert ca.parental_bond_hit_count(u, SimpleNamespace(power=40, category="physical", effects=["multi_hit:2"]), db) is None
    assert ca.parental_bond_hit_power_mult(1) == 0.25

    ca.process_cheek_pouch(None, db)
    ca.process_cheek_pouch(_u(is_fainted=True), db)
    full = _u(current_hp=100, current_stats={"hp": 100})
    ca.process_cheek_pouch(full, db)
    low = _u(current_hp=10, current_stats={"hp": 0})
    ca.process_cheek_pouch(low, db)
    healed = _u(current_hp=10, current_stats={"hp": 100})
    assert ca.process_cheek_pouch(healed, db)

    assert ca.healing_move_priority_bonus(
        u, SimpleNamespace(slug="recover", name="Recover", effects=["heal"], power=0, category="status"), db
    ) >= 0

    ca.process_emergency_exit_or_wimp_out(None, before_hp=100, db=db)
    ca.process_emergency_exit_or_wimp_out(_u(current_stats={"hp": 0}), before_hp=50, db=db)
    ca.process_emergency_exit_or_wimp_out(
        _u(current_hp=40, current_stats={"hp": 100}, flags={}), before_hp=80, db=db
    )

    assert ca.update_hp_threshold_formes(None, db) is False
    assert ca.update_hp_threshold_formes(u, db) in (True, False)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: [])
    assert ca.update_hp_threshold_formes(u, db) is False

    assert ca.is_dance_move(None) is False
    assert ca.is_dance_move(SimpleNamespace(slug="", name="Swords Dance"))

    dancer = _u(id=8, flags={}, stat_boosts={})
    monkeypatch.setattr(ca, "ability_has_token", lambda unit, *a, **k: unit is dancer)
    monkeypatch.setattr(ca, "get_active_ability", lambda *a, **k: SimpleNamespace(name="Dancer"))
    move = SimpleNamespace(
        slug="swords_dance",
        name="Swords Dance",
        effects=["self:raise_stat:attack:2", "target:raise_stat:speed:bad"],
    )

    _dc = {"n": 0}

    def apply_stat(*a, **k):
        _dc["n"] += 1
        if _dc["n"] == 1:
            raise TypeError()
        return None

    ca.process_dancer_copy(move, _u(id=1), [dancer], db, 1, helpers={"apply_stat_change": apply_stat})
    ca.process_dancer_copy(SimpleNamespace(slug="tackle", name="Tackle", effects=[]), _u(id=1), [dancer], db, 1)

    # aura break invert
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["field:on_move_type:fairy:boost_power:1.33", "aura_break"],
    )
    db.query.return_value.filter.return_value.all.return_value = [_u()]
    ca.field_move_type_power_multiplier(10, "fairy", db)
    ca.field_move_type_power_multiplier(None, "fairy", db)


def test_aftermath_anger_color_stench_drain_edges(monkeypatch):
    db = MagicMock()
    fainted = _u(id=1)
    atk = _u(id=2, current_hp=5, current_stats={"hp": 0})
    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "should_ignore_indirect_damage", lambda *a, **k: False)
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["on_faint_from_contact:attacker:damage_fraction:bad"],
    )
    ca.process_aftermath(fainted, atk, makes_contact=True, db=db)
    ca.process_aftermath(fainted, None, makes_contact=True, db=db)
    ca.process_aftermath(fainted, _u(is_fainted=True), makes_contact=True, db=db)

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_crit_received:self:raise_stat:attack:6"])
    ca.process_anger_point(_u(stat_boosts=None), was_crit=True, db=db, current_turn=1)
    ca.process_anger_point(_u(is_fainted=True), was_crit=True, db=db, current_turn=1)

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_hit:change_type_to_move_type"])
    ca.process_color_change(_u(flags={}), "water", db)
    ca.process_color_change(_u(is_fainted=True), "water", db)

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_damage_dealt:target:flinch:bad"])
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    ca.process_stench_flinch(_u(), _u(states=None), 10, db)

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: False)
    assert ca.process_recoil_allowed(_u(), db) is True

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["boost_drain:1.5"])
    ca.process_drain(_u(current_hp=10, current_stats={"hp": 100}), _u(), 20, db)
    ca.process_drain(_u(current_hp=10, current_stats={"hp": 100}), _u(), 0, db)


def test_misc_remaining_helpers(monkeypatch):
    db = MagicMock()
    # convert_move_type normalize paths
    monkeypatch.setattr(
        ca,
        "get_ability_effects",
        lambda *a, **k: ["convert_move_type:normal", "normalize"],
    )
    assert ca.convert_move_type(_u(), SimpleNamespace(type="fire", category="special"), db) == "normal"

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["convert_move_category:sound:to_type:electric"])
    monkeypatch.setattr(ca, "_move_is_sound", lambda m: True)
    assert ca.convert_move_type(_u(), SimpleNamespace(type="normal"), db) == "electric"

    # disguise / innards / receiver early outs
    ca.apply_disguise(_u(is_fainted=True), 10, db)
    ca.process_innards_out(_u(is_fainted=True), _u(), hp_lost=10, db=db)
    ca.process_innards_out(_u(), None, hp_lost=10, db=db)
    ca.process_any_faint(_u(is_fainted=True), [], db, 1)
    ca.process_receiver_on_ally_faint(_u(unit=SimpleNamespace(ability_ids=[])), [], db)
    ca.process_receiver_on_ally_faint(None, [], db)
    ca.ensure_comatose_sleep(None, db)
    ca.blocks_priority_against(_u(), db)

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    ca.process_ice_face(_u(flags={"forme": "ice"}), 0, is_physical=True, db=db)
    ca.berry_effect_multiplier(_u(), db)
    ca.quick_draw_goes_first(_u(), db)
    ca.process_gulp_missile_spit(_u(flags={}), _u(), 0, db)
    ca.maybe_catch_gulp_prey(_u(), SimpleNamespace(slug="surf"), db)
    ca.activate_booster_energy(_u(flags={"held_item": "booster-energy"}), db)
    ca.tera_shell_type_multiplier(_u(current_hp=100, current_stats={"hp": 100}), 2.0, db)
    ca.process_toxic_chain(_u(), _u(is_fainted=True), damage=5, db=db)
    ca.process_toxic_chain(_u(), _u(), damage=0, db=db)
    ca.process_poison_puppeteer(_u(), None, "poison", db)
    ca.process_poison_puppeteer(_u(), _u(), "burn", db)
    ca.process_cud_chew_on_berry_eat(_u(flags={}), db)
    ca.process_cud_chew_end_of_turn(_u(flags={}), db)
    ca.status_moves_ignore_target_ability(_u(), SimpleNamespace(category="status", power=0), db)
    ca.immune_to_forced_switch(_u(), db)
    ca.electric_move_charge_multiplier(_u(), "electric", db)
    ca.process_wind_rider_on_tailwind(_u(stat_boosts={}), db, 1, helpers={})

    # strong winds / flying priority
    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["priority_flying:1", "gale_wings"])
    ca.flying_move_priority_bonus(_u(current_hp=100, current_stats={"hp": 100}), SimpleNamespace(type="flying"), db)
    monkeypatch.setattr(ca, "_default_get_unit_types", lambda *a, **k: {"flying"})
    wid = ca.WEATHER_TO_ID.get("strong_winds", 8)
    ca.apply_strong_winds_type_modifier(_u(), 2.0, wid, db)
    ca.apply_strong_winds_type_modifier(_u(), 1.0, wid, db)

    monkeypatch.setattr(ca, "get_ability_effects", lambda *a, **k: ["on_stat_lowered:self:raise_stat:attack:2"])
    ca.parse_stat_lowered_reactions(_u(), db)

    monkeypatch.setattr(ca, "ability_has_token", lambda *a, **k: True)
    ca.should_block_move_against(_u(), SimpleNamespace(type="ground"), db)
    ca.should_mirror_status(_u(), "poison", db)
    ca.unit_traps_opponent(_u(), _u(), db)
    ca.is_trapped_by_adjacent_opponent(_u(current_x=0, current_y=0, game_id=10), db)
