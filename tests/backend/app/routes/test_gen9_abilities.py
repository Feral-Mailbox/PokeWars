"""Gen 9 ability wiring tests for games.py + combat_abilities."""

import pytest

import app.db.models as models
from app import combat_abilities as ca
from app.routes.games import (
    apply_stat_change,
    apply_status_effect,
    get_stat_stage,
    TERRAIN_TO_ID,
)
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game


@pytest.fixture
def user(db):
    u = models.User(username="gen9-user", email="gen9@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def client(db, user):
    from fastapi.testclient import TestClient
    from app.dependencies import get_current_user, get_db
    from app.main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _ability(db, *, name, slug, effects, generation=9):
    row = models.Ability(
        name=name,
        slug=slug,
        description=name,
        generation=generation,
        effect=effects,
    )
    db.add(row)
    db.flush()
    return row


def _attach_ability(unit: models.GameUnit, ability: models.Ability, db):
    flags = dict(unit.flags or {})
    flags["ability_id"] = ability.id
    unit.flags = flags
    db.add(unit)
    db.flush()


def test_rocky_payload_and_fire_mane(db, user):
    ctx = _create_battle_game(db, user, link="rocky-payload")
    ab = _ability(
        db,
        name="Rocky Payload",
        slug="rocky_payload",
        effects=["on_move_type:rock:self:boost_power:1.5"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()
    rock = models.Move(name="Rock Slide", type="Rock", category="Physical", power=75)
    assert ca.attacker_power_multiplier(unit, rock, db) == pytest.approx(1.5)


def test_earth_eater_absorbs_ground(db, user):
    ctx = _create_battle_game(db, user, link="earth-eater")
    ab = _ability(
        db,
        name="Earth Eater",
        slug="earth_eater",
        effects=["immune:ground", "on_hit:ground:self:heal_fraction:4"],
    )
    unit = ctx["opponent_unit"]
    unit.current_hp = 50
    unit.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    _attach_ability(unit, ab, db)
    db.commit()
    result = ca.handle_type_absorb(unit, "ground", db)
    assert result and result.get("absorbed")
    assert unit.current_hp == 75


def test_well_baked_body_boosts_def_on_fire(db, user):
    ctx = _create_battle_game(db, user, link="well-baked")
    ab = _ability(
        db,
        name="Well-Baked Body",
        slug="well_baked_body",
        effects=["immune:fire", "on_hit:fire:self:raise_stat:defense:2"],
    )
    unit = ctx["opponent_unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, ab, db)
    db.commit()
    result = ca.handle_type_absorb(unit, "fire", db)
    assert result and result.get("raise_stat") == ("defense", 2)


def test_sharpness_boosts_slicing(db, user):
    ctx = _create_battle_game(db, user, link="sharpness")
    ab = _ability(
        db, name="Sharpness", slug="sharpness", effects=["on_move_flag:slicing:self:boost_power:1.5"]
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()
    slash = models.Move(name="Sacred Sword", type="Fighting", category="Physical", power=90)
    tackle = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(unit, slash, db) == pytest.approx(1.5)
    assert ca.attacker_power_multiplier(unit, tackle, db) == 1.0


def test_anger_shell_on_hp_cross(db, user):
    ctx = _create_battle_game(db, user, link="anger-shell")
    ab = _ability(
        db,
        name="Anger Shell",
        slug="anger_shell",
        effects=[
            "on_hp_cross_below:50:self:lower_stat:defense:1",
            "on_hp_cross_below:50:self:raise_stat:attack:1",
            "on_hp_cross_below:50:self:raise_stat:speed:1",
        ],
    )
    defender = ctx["opponent_unit"]
    defender.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    defender.current_hp = 40
    defender.stat_boosts = {}
    _attach_ability(defender, ab, db)
    db.commit()

    def _simple_stat(unit, stat, magnitude, current_turn, db, **kwargs):
        boosts = getattr(unit, "stat_boosts", None)
        if not isinstance(boosts, dict):
            boosts = {}
        instances = list(boosts.get(stat) or [])
        instances.append({"magnitude": magnitude, "expires_turn": 4})
        boosts = dict(boosts)
        boosts[stat] = instances
        unit.stat_boosts = boosts
        db.add(unit)

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    msgs = ca.process_defender_hit_reactions(
        ctx["unit"],
        defender,
        move,
        damage=20,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_stat_change": _simple_stat},
        before_hp=60,
    )
    assert any("defense" in m.lower() for m in msgs)
    assert any("attack" in m.lower() for m in msgs)
    assert get_stat_stage(defender.stat_boosts, "defense") == -1
    assert get_stat_stage(defender.stat_boosts, "attack") == 1
    assert get_stat_stage(defender.stat_boosts, "speed") == 1


def test_seed_sower_sets_grassy(db, user):
    ctx = _create_battle_game(db, user, link="seed-sower")
    ab = _ability(db, name="Seed Sower", slug="seed_sower", effects=["on_damage_taken:terrain:grassy"])
    defender = ctx["opponent_unit"]
    _attach_ability(defender, ab, db)
    db.commit()

    class FakeMap:
        terrain_effect_tiles = [[[0, 0] for _ in range(6)] for _ in range(6)]

    map_state = FakeMap()
    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    msgs = ca.process_defender_hit_reactions(
        ctx["unit"],
        defender,
        move,
        damage=10,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"map_state": map_state},
    )
    assert msgs
    cell = map_state.terrain_effect_tiles[0][0]
    assert cell[0] == TERRAIN_TO_ID["grassy"]


def test_sword_of_ruin_lowers_others_defense(db, user):
    ctx = _create_battle_game(db, user, link="sword-ruin")
    ruin = _ability(
        db, name="Sword of Ruin", slug="sword_of_ruin", effects=["field_others:boost_stat_mult:defense:0.75"]
    )
    holder = ctx["unit"]
    target = ctx["opponent_unit"]
    _attach_ability(holder, ruin, db)
    db.commit()

    base = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    out = ca.modify_effective_stats(target, base, db)
    assert out["defense"] == 75
    # Holder itself is unaffected
    out_self = ca.modify_effective_stats(holder, base, db)
    assert out_self["defense"] == 100


def test_protosynthesis_boosts_highest_in_sun(db, user):
    ctx = _create_battle_game(db, user, link="protosynthesis")
    ab = _ability(
        db,
        name="Protosynthesis",
        slug="protosynthesis",
        effects=["on_weather:sun:boost_highest_stat:1.3"],
    )
    unit = ctx["unit"]
    unit.current_stats = {
        "hp": 100,
        "attack": 80,
        "defense": 40,
        "sp_attack": 50,
        "sp_defense": 40,
        "speed": 60,
    }
    _attach_ability(unit, ab, db)
    db.commit()

    base = dict(unit.current_stats)
    weather = [[ca.WEATHER_TO_ID["sun"] for _ in range(6)] for _ in range(6)]
    out = ca.modify_effective_stats(unit, base, db, weather_tiles=weather)
    assert out["attack"] == int(80 * 1.3)


def test_quark_drive_on_electric_terrain(db, user):
    ctx = _create_battle_game(db, user, link="quark-drive")
    ab = _ability(
        db,
        name="Quark Drive",
        slug="quark_drive",
        effects=["on_terrain:electric:boost_highest_stat:1.3"],
    )
    unit = ctx["unit"]
    unit.current_stats = {
        "hp": 100,
        "attack": 40,
        "defense": 40,
        "sp_attack": 90,
        "sp_defense": 40,
        "speed": 50,
    }
    _attach_ability(unit, ab, db)
    db.commit()
    base = dict(unit.current_stats)
    terrain = [[[TERRAIN_TO_ID["electric"], 5] for _ in range(6)] for _ in range(6)]
    out = ca.modify_effective_stats(unit, base, db, terrain_tiles=terrain)
    assert out["sp_attack"] == int(90 * 1.3)


def test_supersweet_syrup_once_per_battle(db, user):
    ctx = _create_battle_game(db, user, link="supersweet")
    ab = _ability(
        db,
        name="Supersweet Syrup",
        slug="supersweet_syrup",
        effects=["on_switch_in:opponents:lower_stat:evasion:1:once_per_battle"],
    )
    unit = ctx["unit"]
    opp = ctx["opponent_unit"]
    opp.stat_boosts = {}
    _attach_ability(unit, ab, db)
    db.commit()

    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert get_stat_stage(opp.stat_boosts, "evasion") == -1

    opp.stat_boosts = {}
    db.add(opp)
    db.flush()
    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=2,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert get_stat_stage(opp.stat_boosts, "evasion") == 0


def test_hospitality_heals_ally(db, user):
    ctx = _create_battle_game(db, user, link="hospitality")
    ab = _ability(
        db, name="Hospitality", slug="hospitality", effects=["on_switch_in:ally:heal_fraction:4"]
    )
    unit = ctx["unit"]
    ally = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=user.id,
        unit_id=unit.unit_id,
        level=unit.level,
        starting_x=2,
        starting_y=2,
        current_x=2,
        current_y=2,
        current_hp=50,
        current_stats={"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50},
        is_fainted=False,
        can_move=True,
        flags={},
        stat_boosts={},
        status_effects=[],
        states=[],
        move_pp=[5, 5, 5, 5],
    )
    db.add(ally)
    db.flush()
    _attach_ability(unit, ab, db)
    db.commit()

    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={},
    )
    assert ally.current_hp == 75


def test_costar_copies_ally_boosts(db, user):
    ctx = _create_battle_game(db, user, link="costar")
    ab = _ability(
        db,
        name="Costar",
        slug="costar",
        effects=["on_switch_in:self:copy_stat_changes:ally"],
    )
    unit = ctx["unit"]
    unit.stat_boosts = {}
    ally = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=user.id,
        unit_id=unit.unit_id,
        level=unit.level,
        starting_x=2,
        starting_y=2,
        current_x=2,
        current_y=2,
        current_hp=100,
        current_stats=dict(unit.current_stats or {}),
        is_fainted=False,
        can_move=True,
        flags={},
        stat_boosts={"speed": [{"magnitude": 2, "expires_turn": 4}]},
        status_effects=[],
        states=[],
        move_pp=[5, 5, 5, 5],
    )
    db.add(ally)
    db.flush()
    _attach_ability(unit, ab, db)
    db.commit()

    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={},
    )
    assert get_stat_stage(unit.stat_boosts, "speed") == 2


def test_supreme_overlord_stores_boost(db, user):
    ctx = _create_battle_game(db, user, link="supreme-overlord")
    ab = _ability(
        db,
        name="Supreme Overlord",
        slug="supreme_overlord",
        effects=["on_switch_in:boost_power_per_fainted_ally:0.1:max:0.5"],
    )
    unit = ctx["unit"]
    fainted = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=user.id,
        unit_id=unit.unit_id,
        level=unit.level,
        starting_x=3,
        starting_y=3,
        current_x=3,
        current_y=3,
        current_hp=0,
        current_stats=dict(unit.current_stats or {}),
        is_fainted=True,
        can_move=False,
        flags={},
        stat_boosts={},
        status_effects=[],
        states=[],
        move_pp=[5, 5, 5, 5],
    )
    db.add(fainted)
    db.flush()
    _attach_ability(unit, ab, db)
    db.commit()

    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={},
    )
    assert (unit.flags or {}).get("supreme_overlord_boost") == pytest.approx(0.1)
    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(unit, move, db) == pytest.approx(1.1)


def test_good_as_gold_blocks_status(db, user):
    ctx = _create_battle_game(db, user, link="good-as-gold")
    ab = _ability(
        db, name="Good as Gold", slug="good_as_gold", effects=["immune_category:status_moves"]
    )
    target = ctx["opponent_unit"]
    _attach_ability(target, ab, db)
    db.commit()
    status = models.Move(name="Will-O-Wisp", type="Fire", category="Status", power=0)
    assert ca.should_block_move_against(target, status, db) == "good_as_gold"


def test_wind_rider_blocks_and_raises(db, user):
    ctx = _create_battle_game(db, user, link="wind-rider")
    ab = _ability(
        db,
        name="Wind Rider",
        slug="wind_rider",
        effects=[
            "immune_category:wind",
            "on_hit_category:wind:self:raise_stat:attack:1",
            "on_tailwind:self:raise_stat:attack:1",
        ],
    )
    unit = ctx["opponent_unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, ab, db)
    db.commit()

    gust = models.Move(name="Gust", type="Flying", category="Special", power=40)
    assert ca.should_block_move_against(unit, gust, db) == "wind_rider"

    msgs = ca.process_wind_rider_on_tailwind(
        unit, db, 1, helpers={"apply_stat_change": apply_stat_change}
    )
    assert msgs
    assert get_stat_stage(unit.stat_boosts, "attack") == 1


def test_electromorphosis_applies_charge(db, user):
    ctx = _create_battle_game(db, user, link="electromorphosis")
    ab = _ability(
        db,
        name="Electromorphosis",
        slug="electromorphosis",
        effects=["on_damage_taken:self:apply_state:charge"],
    )
    defender = ctx["opponent_unit"]
    defender.states = []
    _attach_ability(defender, ab, db)
    db.commit()
    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    from app.routes.games import apply_state_effect

    ca.process_defender_hit_reactions(
        ctx["unit"],
        defender,
        move,
        damage=10,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_state_effect": apply_state_effect},
    )
    assert defender.states and defender.states[0] == "charge"


def test_charge_doubles_electric(db, user):
    ctx = _create_battle_game(db, user, link="charge-mult")
    unit = ctx["unit"]
    unit.states = ["charge", 2]
    db.commit()
    assert ca.electric_move_charge_multiplier(unit, "electric", db) == 2.0
    assert not unit.states
    assert ca.electric_move_charge_multiplier(unit, "electric", db) == 1.0


def test_toxic_chain_poisons(db, user, monkeypatch):
    ctx = _create_battle_game(db, user, link="toxic-chain")
    ab = _ability(
        db,
        name="Toxic Chain",
        slug="toxic_chain",
        effects=["on_damage_dealt:target:status:badly_poison:100"],
    )
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    target.status_effects = []
    _attach_ability(attacker, ab, db)
    db.commit()
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    msgs = ca.process_toxic_chain(
        attacker,
        target,
        damage=20,
        db=db,
        helpers={"apply_status_effect": apply_status_effect},
    )
    assert msgs
    assert target.status_effects[0] == "badly_poisoned"


def test_spicy_spray_burns_attacker(db, user):
    ctx = _create_battle_game(db, user, link="spicy-spray")
    ab = _ability(
        db, name="Spicy Spray", slug="spicy_spray", effects=["on_damage_taken:attacker:status:burn"]
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.status_effects = []
    _attach_ability(defender, ab, db)
    db.commit()
    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=15,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_status_effect": apply_status_effect},
    )
    assert attacker.status_effects and attacker.status_effects[0] == "burn"


def test_tera_shell_forces_nve_at_full_hp(db, user):
    ctx = _create_battle_game(db, user, link="tera-shell")
    ab = _ability(
        db,
        name="Tera Shell",
        slug="tera_shell",
        effects=["on_hp_full:all_damaging_moves:not_very_effective"],
    )
    unit = ctx["opponent_unit"]
    unit.current_hp = 100
    unit.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    _attach_ability(unit, ab, db)
    db.commit()
    assert ca.tera_shell_type_multiplier(unit, 2.0, db) == 0.5
    unit.current_hp = 50
    assert ca.tera_shell_type_multiplier(unit, 2.0, db) == 2.0


def test_tera_shift_and_zero_to_hero(db, user):
    ctx = _create_battle_game(db, user, link="tera-shift")
    shift = _ability(
        db, name="Tera Shift", slug="tera_shift", effects=["on_switch_in:change_forme:terastal"]
    )
    unit = ctx["unit"]
    _attach_ability(unit, shift, db)
    db.commit()
    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={},
    )
    assert (unit.flags or {}).get("forme") == "terastal"

    hero = _ability(
        db, name="Zero to Hero", slug="zero_to_hero", effects=["on_switch_out:change_forme:hero"]
    )
    _attach_ability(unit, hero, db)
    db.commit()
    assert ca.process_switch_out_or_faint(unit, db, fainted=False) is True
    assert (unit.flags or {}).get("forme") == "hero"


def test_opportunist_copies_boost(db, user):
    ctx = _create_battle_game(db, user, link="opportunist")
    ab = _ability(
        db,
        name="Opportunist",
        slug="opportunist",
        effects=["on_opponent_stat_boost:copy_stat_boosts"],
    )
    opp = ctx["opponent_unit"]
    unit = ctx["unit"]
    opp.stat_boosts = {}
    unit.stat_boosts = {}
    _attach_ability(opp, ab, db)
    db.commit()

    apply_stat_change(unit, "attack", 1, 1, db, from_opponent=False)
    assert get_stat_stage(opp.stat_boosts, "attack") == 1


def test_poison_puppeteer_confuses(db, user):
    ctx = _create_battle_game(db, user, link="poison-puppeteer")
    ab = _ability(
        db,
        name="Poison Puppeteer",
        slug="poison_puppeteer",
        effects=["on_poison_dealt:also:apply_state:confusion"],
    )
    source = ctx["unit"]
    target = ctx["opponent_unit"]
    target.states = []
    _attach_ability(source, ab, db)
    db.commit()
    from app.routes.games import apply_state_effect

    msgs = ca.process_poison_puppeteer(
        source,
        target,
        "poison",
        db,
        helpers={"apply_state_effect": apply_state_effect},
    )
    assert msgs
    assert target.states[0] == "confusion"


def test_cud_chew_queues_and_reuses(db, user):
    ctx = _create_battle_game(db, user, link="cud-chew")
    ab = _ability(db, name="Cud Chew", slug="cud_chew", effects=["on_berry_eat:reuse_next_turn"])
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    flags = dict(unit.flags or {})
    flags["last_consumed_berry"] = "oran-berry"
    unit.flags = flags
    db.commit()

    assert ca.process_cud_chew_on_berry_eat(unit, db) is True
    assert (unit.flags or {}).get("cud_chew_pending") is True
    msgs = ca.process_cud_chew_end_of_turn(unit, db)
    assert msgs
    assert "cud_chew_pending" not in (unit.flags or {})


def test_mega_sol_treats_weather_as_sun(db, user):
    ctx = _create_battle_game(db, user, link="mega-sol")
    ab = _ability(db, name="Mega Sol", slug="mega_sol", effects=["treat_weather_as:sun"])
    pulse = _ability(
        db,
        name="Orichalcum Pulse",
        slug="orichalcum_pulse",
        effects=["on_weather:sun:self:boost_stat_mult:attack:1.333"],
    )
    # Mega Sol alone doesn't boost; combine with orichalcum weather mult on same unit via treat as sun
    unit = ctx["unit"]
    # Attach mega sol + use a sun attack boost token via fallback by putting both effects on one ability
    combo = _ability(
        db,
        name="Mega Sol Combo",
        slug="mega_sol_combo",
        effects=["treat_weather_as:sun", "on_weather:sun:self:boost_stat_mult:attack:1.333"],
    )
    _attach_ability(unit, combo, db)
    db.commit()
    base = {"hp": 100, "attack": 99, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    out = ca.modify_effective_stats(unit, base, db, weather_tiles=None)
    assert out["attack"] == int(99 * 1.333)


def test_embody_aspect_raises_on_switch_in(db, user):
    ctx = _create_battle_game(db, user, link="embody-aspect")
    ab = _ability(
        db,
        name="Embody Aspect",
        slug="embody_aspect_teal_mask",
        effects=["on_switch_in:self:raise_stat:speed:1"],
    )
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, ab, db)
    db.commit()
    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert get_stat_stage(unit.stat_boosts, "speed") == 1


def test_dragonize_converts_normal(db, user):
    ctx = _create_battle_game(db, user, link="dragonize")
    ab = _ability(
        db,
        name="Dragonize",
        slug="dragonize",
        effects=["convert_move_type:normal:to:dragon", "on_converted_type:self:boost_power:1.2"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()
    normal = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.convert_move_type(unit, normal, db) == "dragon"
    assert ca.attacker_power_multiplier(unit, normal, db) == pytest.approx(1.2)


def test_purifying_salt_and_thermal_exchange(db, user):
    ctx = _create_battle_game(db, user, link="purifying-salt")
    ab = _ability(
        db,
        name="Purifying Salt",
        slug="purifying_salt",
        effects=["on_hit_type:ghost:self:resist:0.5", "immune_status:all"],
    )
    unit = ctx["opponent_unit"]
    _attach_ability(unit, ab, db)
    db.commit()
    ghost = models.Move(name="Shadow Ball", type="Ghost", category="Special", power=80)
    assert ca.defender_damage_multiplier(unit, ghost, "ghost", 1.0, db) == 0.5
    assert ca.can_apply_status(unit, "burn", db) is False


def test_mycelium_might_status_ignores_ability(db, user):
    ctx = _create_battle_game(db, user, link="mycelium")
    ab = _ability(
        db,
        name="Mycelium Might",
        slug="mycelium_might",
        effects=["status_moves:force_last", "status_moves:ignore_target_ability"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()
    status = models.Move(name="Spore", type="Grass", category="Status", power=0)
    assert ca.status_moves_ignore_target_ability(unit, status, db) is True
    tackle = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.status_moves_ignore_target_ability(unit, tackle, db) is False


def test_guard_dog_and_piercing_helpers(db, user):
    ctx = _create_battle_game(db, user, link="guard-dog")
    dog = _ability(
        db,
        name="Guard Dog",
        slug="guard_dog",
        effects=["on_intimidate:self:raise_stat:attack:1", "immune_forced_switch"],
    )
    drill = _ability(
        db, name="Piercing Drill", slug="piercing_drill", effects=["contact_bypass_protect:0.25"]
    )
    unit = ctx["unit"]
    _attach_ability(unit, dog, db)
    db.commit()
    assert ca.immune_to_forced_switch(unit, db) is True
    _attach_ability(unit, drill, db)
    db.commit()
    assert ca.contact_bypasses_protect(unit, db) is True
