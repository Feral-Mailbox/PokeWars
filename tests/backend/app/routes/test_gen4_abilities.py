"""Gen 4 ability wiring tests for games.py + combat_abilities."""

import pytest

import app.db.models as models
from app import combat_abilities as ca
from app.routes.games import (
    apply_end_of_round_weather_damage,
    apply_end_of_turn_status_damage,
    apply_stat_change,
    get_move_hit_count,
    get_stat_stage,
    move_lands_on_target,
    WEATHER_TO_ID,
)
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game


@pytest.fixture
def user(db):
    u = models.User(username="gen4-user", email="gen4@example.com", hashed_password="x")
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


def _ability(db, *, name, slug, effects, ability_id=None, generation=4):
    row = models.Ability(
        id=ability_id,
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


def test_technician_boosts_low_power(db, user):
    ctx = _create_battle_game(db, user, link="tech-power")
    tech = _ability(
        db,
        name="Technician",
        slug="technician",
        effects=["on_move_power_at_most:60:self:boost_power:1.5"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, tech, db)
    db.commit()

    low = models.Move(name="Quick Attack", type="Normal", category="Physical", power=40)
    high = models.Move(name="Body Slam", type="Normal", category="Physical", power=80)
    assert ca.attacker_power_multiplier(attacker, low, db) == 1.5
    assert ca.attacker_power_multiplier(attacker, high, db) == 1.0


def test_filter_reduces_se_damage(db, user):
    ctx = _create_battle_game(db, user, link="filter-se")
    filt = _ability(
        db,
        name="Filter",
        slug="filter",
        effects=["on_super_effective:self:resist:0.75"],
    )
    target = ctx["opponent_unit"]
    _attach_ability(target, filt, db)
    db.commit()

    move = models.Move(name="Earthquake", type="Ground", category="Physical", power=100)
    assert ca.defender_damage_multiplier(target, move, "ground", 2.0, db) == 0.75
    assert ca.defender_damage_multiplier(target, move, "ground", 1.0, db) == 1.0


def test_adaptability_stab_2(db, user):
    ctx = _create_battle_game(db, user, link="adapt-stab")
    adapt = _ability(db, name="Adaptability", slug="adaptability", effects=["boost_stab:2"])
    attacker = ctx["unit"]
    _attach_ability(attacker, adapt, db)
    db.commit()

    assert ca.get_stab_multiplier(attacker, "normal", {"normal"}, db) == 2.0
    assert ca.get_stab_multiplier(attacker, "fire", {"normal"}, db) == 1.0


def test_storm_drain_redirects_water(db, user):
    ctx = _create_battle_game(db, user, link="storm-drain")
    drain = _ability(
        db,
        name="Storm Drain",
        slug="storm_drain",
        effects=["redirect:water", "immune:water", "on_hit:water:self:raise_stat:special_attack:1"],
    )
    redirector = ctx["opponent_unit"]
    _attach_ability(redirector, drain, db)
    db.commit()

    move = models.Move(name="Water Gun", type="Water", category="Special", power=40)
    attacker = ctx["unit"]
    all_units = [attacker, redirector]
    redirected = ca.redirect_targets_for_move(move, attacker, [attacker], all_units, db)
    assert redirected == [redirector]


def test_download_raises_spa_or_atk(db, user):
    ctx = _create_battle_game(db, user, link="download-sw")
    download = _ability(
        db,
        name="Download",
        slug="download",
        effects=["on_switch_in:self:raise_stat:attack_or_special_attack:better_vs_opponent"],
    )
    unit = ctx["unit"]
    opp = ctx["opponent_unit"]
    opp.current_stats = {
        **(opp.current_stats or {}),
        "defense": 100,
        "sp_defense": 40,
    }
    unit.stat_boosts = {}
    _attach_ability(unit, download, db)
    db.commit()

    msgs = ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(unit.stat_boosts, "sp_attack") == 1


def test_skill_link_max_hits(db, user):
    ctx = _create_battle_game(db, user, link="skill-link")
    skill = _ability(db, name="Skill Link", slug="skill_link", effects=["multi_hit:always_max"])
    attacker = ctx["unit"]
    _attach_ability(attacker, skill, db)
    db.commit()

    move = models.Move(
        name="Bullet Seed",
        type="Grass",
        category="Physical",
        power=25,
        effects=["multi_hit:2:5"],
    )
    assert ca.force_max_multi_hit(attacker, db) is True
    assert get_move_hit_count(move, force_max=True) == 5


def test_no_guard_never_miss(db, user):
    ctx = _create_battle_game(db, user, link="no-guard")
    ng = _ability(
        db,
        name="No Guard",
        slug="no_guard",
        effects=["moves_never_miss", "opponent_moves_never_miss"],
    )
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    _attach_ability(attacker, ng, db)
    db.commit()

    move = models.Move(name="Zap Cannon", type="Electric", category="Special", power=120, accuracy=50)
    assert ca.force_move_never_miss(attacker, target, db) is True
    assert move_lands_on_target(move, attacker, target, db=db) is True


def test_magic_guard_blocks_weather_damage(db, user):
    ctx = _create_battle_game(db, user, link="magic-guard")
    mg = _ability(db, name="Magic Guard", slug="magic_guard", effects=["immune_indirect_damage"])
    unit = ctx["unit"]
    _attach_ability(unit, mg, db)

    map_state = ctx["map_state"]
    w = WEATHER_TO_ID["sandstorm"]
    map_state.weather_tiles = [[w for _ in range(6)] for _ in range(6)]
    db.add(map_state)

    unit.current_stats = {**(unit.current_stats or {}), "hp": 100}
    unit.current_hp = 100
    opp = ctx["opponent_unit"]
    opp.current_stats = {**(opp.current_stats or {}), "hp": 100}
    opp.current_hp = 100
    db.commit()

    modified = apply_end_of_round_weather_damage(ctx["game"].id, db)
    db.flush()
    db.refresh(unit)
    db.refresh(opp)
    assert unit.current_hp == 100
    assert opp.current_hp < 100
    assert unit.id not in modified


def test_poison_heal_heals_instead_of_poison_damage(db, user):
    ctx = _create_battle_game(db, user, link="poison-heal")
    ph = _ability(
        db,
        name="Poison Heal",
        slug="poison_heal",
        effects=[
            "on_status:poison:on_turn_end:self:heal_fraction:8",
            "ignore_poison_damage",
        ],
    )
    unit = ctx["unit"]
    unit.current_stats = {**(unit.current_stats or {}), "hp": 80}
    unit.current_hp = 40
    unit.status_effects = ["poison", 5]
    _attach_ability(unit, ph, db)
    db.commit()

    apply_end_of_turn_status_damage(unit.user_id, ctx["game"].id, db)
    db.flush()
    db.refresh(unit)
    assert unit.current_hp == 40  # no poison chip

    ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        weather_tiles=None,
        current_turn=1,
    )
    db.flush()
    db.refresh(unit)
    assert unit.current_hp == 50  # healed 80/8


def test_aftermath_damages_attacker_on_contact_ko(db, user):
    ctx = _create_battle_game(db, user, link="aftermath")
    aftermath = _ability(
        db,
        name="Aftermath",
        slug="aftermath",
        effects=["on_faint_from_contact:attacker:damage_fraction:4"],
    )
    fainted = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.current_stats = {**(attacker.current_stats or {}), "hp": 100}
    attacker.current_hp = 100
    _attach_ability(fainted, aftermath, db)
    db.commit()

    msgs = ca.process_aftermath(fainted, attacker, makes_contact=True, db=db)
    assert msgs
    db.flush()
    db.refresh(attacker)
    assert attacker.current_hp == 75


def test_anger_point_on_crit(db, user):
    ctx = _create_battle_game(db, user, link="anger-point")
    ap = _ability(
        db,
        name="Anger Point",
        slug="anger_point",
        effects=["on_crit_received:self:raise_stat:attack:6"],
    )
    defender = ctx["opponent_unit"]
    defender.stat_boosts = {}
    _attach_ability(defender, ap, db)
    db.commit()

    msgs = ca.process_anger_point(
        defender,
        was_crit=True,
        db=db,
        current_turn=1,
        apply_stat_change=apply_stat_change,
    )
    assert msgs
    assert get_stat_stage(defender.stat_boosts, "attack") == 6


def test_simple_doubles_stat_changes(db, user):
    ctx = _create_battle_game(db, user, link="simple-stats")
    simple = _ability(db, name="Simple", slug="simple", effects=["double_stat_changes"])
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, simple, db)
    db.commit()

    apply_stat_change(unit, "attack", 1, 1, db)
    assert get_stat_stage(unit.stat_boosts, "attack") == 2


def test_mold_breaker_bypasses_levitate(db, user):
    ctx = _create_battle_game(db, user, link="mold-breaker")
    mb = _ability(db, name="Mold Breaker", slug="mold_breaker", effects=["ignore_target_ability"])
    lev = _ability(db, name="Levitate", slug="levitate", effects=["immune:ground"], generation=3)
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    _attach_ability(attacker, mb, db)
    _attach_ability(target, lev, db)
    db.commit()

    assert ca.should_ignore_target_ability(attacker, db) is True
    # With mold breaker, games.py skips modify_type_multiplier; ability still reports immune alone
    assert ca.modify_type_multiplier(target, "ground", 1.0, db) == 0.0


def test_mold_breaker_bypasses_water_absorb_path(db, user):
    ctx = _create_battle_game(db, user, link="mold-absorb")
    mb = _ability(db, name="Mold Breaker", slug="mold_breaker", effects=["ignore_target_ability"])
    absorb = _ability(
        db,
        name="Water Absorb",
        slug="water_absorb",
        effects=["immune:water", "on_hit:water:self:heal_fraction:4"],
        generation=3,
    )
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    target.current_hp = 50
    target.current_stats = {**(target.current_stats or {}), "hp": 100}
    _attach_ability(attacker, mb, db)
    _attach_ability(target, absorb, db)
    db.commit()

    assert ca.should_ignore_target_ability(attacker, db) is True
    # Absorb still works when called directly; mold breaker skips the call site
    result = ca.handle_type_absorb(target, "water", db)
    assert result and result["absorbed"] is True


def test_hydration_cures_in_rain(db, user):
    ctx = _create_battle_game(db, user, link="hydration")
    hyd = _ability(
        db,
        name="Hydration",
        slug="hydration",
        effects=["on_weather:rain:on_turn_end:self:cure_status"],
    )
    unit = ctx["unit"]
    unit.status_effects = ["burn", 5]
    _attach_ability(unit, hyd, db)

    map_state = ctx["map_state"]
    w = WEATHER_TO_ID["rain"]
    map_state.weather_tiles = [[w for _ in range(6)] for _ in range(6)]
    db.add(map_state)
    db.commit()

    ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        weather_tiles=map_state.weather_tiles,
        current_turn=1,
    )
    db.flush()
    db.refresh(unit)
    assert not unit.status_effects or (
        isinstance(unit.status_effects, list) and len(unit.status_effects) == 0
    )


def test_leaf_guard_blocks_status_in_sun(db, user):
    ctx = _create_battle_game(db, user, link="leaf-guard")
    lg = _ability(
        db,
        name="Leaf Guard",
        slug="leaf_guard",
        effects=["on_weather:sun:immune_status:all"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, lg, db)

    map_state = ctx["map_state"]
    w = WEATHER_TO_ID["sun"]
    map_state.weather_tiles = [[w for _ in range(6)] for _ in range(6)]
    db.add(map_state)
    db.commit()

    assert ca.can_apply_status(unit, "poison", db) is False


def test_snow_warning_sets_hail(db, user):
    ctx = _create_battle_game(db, user, link="snow-warning")
    sw = _ability(
        db,
        name="Snow Warning",
        slug="snow_warning",
        effects=["on_switch_in:weather:hail"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, sw, db)
    db.commit()

    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx["map_state"],
        current_turn=1,
        helpers={"WEATHER_TO_ID": WEATHER_TO_ID},
    )
    db.flush()
    db.refresh(ctx["map_state"])
    tiles = ctx["map_state"].weather_tiles
    assert tiles[0][0] == WEATHER_TO_ID["hail"]
