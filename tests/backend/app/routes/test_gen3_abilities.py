"""Gen 3 ability wiring tests for games.py + combat_abilities."""

import pytest

import app.db.models as models
from app import combat_abilities as ca
from app.routes.games import (
    apply_damage_based_move_effects,
    apply_end_of_round_weather_damage,
    apply_stat_change,
    compute_effective_stats,
    get_stat_stage,
    get_unit_types,
    process_move_effects,
    WEATHER_TO_ID,
)
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game


@pytest.fixture
def user(db):
    u = models.User(username="gen3-user", email="gen3@example.com", hashed_password="x")
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


def _ability(db, *, name, slug, effects, ability_id=None):
    row = models.Ability(
        id=ability_id,
        name=name,
        slug=slug,
        description=name,
        generation=3,
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


def test_levitate_blocks_ground_type_mult(db, user):
    ctx = _create_battle_game(db, user, link="levitate-mult")
    lev = _ability(db, name="Levitate", slug="levitate", effects=["immune:ground", "immune_hazard:spikes"])
    target = ctx["opponent_unit"]
    _attach_ability(target, lev, db)

    mult = ca.modify_type_multiplier(target, "ground", 1.0, db)
    assert mult == 0.0
    assert "flying" not in get_unit_types(target, db)


def test_water_absorb_heals_instead_of_damage(db, user):
    ctx = _create_battle_game(db, user, link="water-absorb")
    absorb = _ability(
        db,
        name="Water Absorb",
        slug="water_absorb",
        effects=["immune:water", "on_hit:water:self:heal_fraction:4"],
    )
    target = ctx["opponent_unit"]
    target.current_hp = 50
    target.current_stats = {**(target.current_stats or {}), "hp": 100}
    _attach_ability(target, absorb, db)
    db.commit()

    result = ca.handle_type_absorb(target, "water", db)
    assert result and result["absorbed"] is True
    assert target.current_hp == 75


def test_blaze_power_at_low_hp(db, user):
    ctx = _create_battle_game(db, user, link="blaze-power")
    blaze = _ability(
        db,
        name="Blaze",
        slug="blaze",
        effects=["on_hp_below:33:on_move_type:fire:self:boost_power:1.5"],
    )
    attacker = ctx["unit"]
    attacker.current_stats = {**(attacker.current_stats or {}), "hp": 100}
    attacker.current_hp = 30
    _attach_ability(attacker, blaze, db)
    db.commit()

    move = models.Move(name="Ember", type="Fire", category="Special", power=40)
    assert ca.attacker_power_multiplier(attacker, move, db) == 1.5

    attacker.current_hp = 50
    assert ca.attacker_power_multiplier(attacker, move, db) == 1.0


def test_intimidate_on_place_unit(client, db, user):
    ctx = _create_battle_game(db, user, link="intimidate-place", status=models.GameStatus.open)
    player = ctx["player"]
    player.cash_remaining = 5000
    player.game_units = []
    db.add(player)

    opp = ctx["opponent_unit"]
    opp.stat_boosts = {}
    opp.current_stats = compute_effective_stats(opp, db)
    db.add(opp)

    intimidate = _ability(
        db,
        name="Intimidate",
        slug="intimidate",
        effects=["on_switch_in:opponents:lower_stat:attack:1"],
    )
    move = models.Move(name="Scratch", type="Normal", category="Physical", pp=20, power=40)
    db.add(move)
    db.flush()
    info = models.Unit(
        species_id=99101,
        name="IntimPlace",
        species="IntimPlace",
        asset_folder="intim",
        types=["Normal"],
        base_stats={"hp": 50, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50, "range": 2},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[move.id],
        ability_ids=[intimidate.id],
        cost=100,
    )
    db.add(info)
    db.commit()

    resp = client.post(
        f"/games/{ctx['game'].link}/units/place",
        json={
            "unit_id": info.id,
            "x": 1,
            "y": 1,
            "current_hp": 1,
            "is_fainted": False,
            "status_effects": [],
            "states": [],
        },
    )
    assert resp.status_code == 200

    db.refresh(opp)
    assert get_stat_stage(opp.stat_boosts, "attack") == -1


def test_sturdy_survives_full_hp_ohko_damage(db, user):
    ctx = _create_battle_game(db, user, link="sturdy-survive")
    sturdy = _ability(
        db,
        name="Sturdy",
        slug="sturdy",
        effects=["endure_ohko_at_full_hp", "immune_category:ohko"],
    )
    target = ctx["opponent_unit"]
    target.current_stats = {**(target.current_stats or {}), "hp": 100}
    target.current_hp = 100
    _attach_ability(target, sturdy, db)
    db.commit()

    damage = ca.apply_sturdy(target, 999, was_full_hp=True, is_ohko=False, db=db)
    assert damage == 99


def test_static_contact_paralysis(db, user, monkeypatch):
    ctx = _create_battle_game(db, user, link="static-contact")
    static = _ability(
        db,
        name="Static",
        slug="static",
        effects=["on_contact:attacker:status:paralysis:30"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.status_effects = []
    _attach_ability(defender, static, db)
    db.commit()

    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    msgs = ca.process_contact_abilities(
        attacker, defender, makes_contact=True, damage=10, db=db
    )
    assert msgs
    assert attacker.status_effects and attacker.status_effects[0] == "paralysis"


def test_air_lock_suppresses_weather_chip(db, user):
    ctx = _create_battle_game(db, user, link="airlock-weather")
    air_lock = _ability(db, name="Air Lock", slug="air_lock", effects=["suppress_weather"])
    unit = ctx["unit"]
    _attach_ability(unit, air_lock, db)

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

    assert ca.weather_is_suppressed(ctx["game"].id, db) is True
    modified = apply_end_of_round_weather_damage(ctx["game"].id, db)
    assert modified == []
    db.refresh(unit)
    assert unit.current_hp == 100


def test_shield_dust_blocks_secondary_status(db, user):
    ctx = _create_battle_game(db, user, link="shield-dust")
    shield = _ability(db, name="Shield Dust", slug="shield_dust", effects=["immune_additional_effects"])
    target = ctx["opponent_unit"]
    target.status_effects = []
    target.current_hp = 80
    _attach_ability(target, shield, db)

    move = models.Move(
        name="Body Slam",
        type="Normal",
        category="Physical",
        power=80,
        effects=["target:status:paralysis:100"],
    )
    attacker = ctx["unit"]
    db.commit()

    process_move_effects(move, attacker, [target], 0, db)
    assert not target.status_effects


def test_rock_head_blocks_recoil(db, user):
    ctx = _create_battle_game(db, user, link="rock-head")
    rock_head = _ability(db, name="Rock Head", slug="rock_head", effects=["immune_recoil"])
    attacker = ctx["unit"]
    attacker.current_hp = 100
    attacker.current_stats = {**(attacker.current_stats or {}), "hp": 100}
    _attach_ability(attacker, rock_head, db)

    move = models.Move(
        name="Take Down",
        type="Normal",
        category="Physical",
        power=90,
        effects=["self:recoil:damage_dealt:4"],
    )
    target = ctx["opponent_unit"]
    db.commit()

    assert ca.process_recoil_allowed(attacker, db) is False
    apply_damage_based_move_effects(
        move,
        attacker,
        [target],
        [{"id": target.id, "damage": 40, "current_hp": 60}],
        db,
    )
    assert attacker.current_hp == 100


def test_apply_stat_change_blocked_by_clear_body(db, user):
    ctx = _create_battle_game(db, user, link="clear-body")
    clear = _ability(db, name="Clear Body", slug="clear_body", effects=["immune_stat_drop"])
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, clear, db)
    db.commit()

    apply_stat_change(unit, "attack", -1, 0, db)
    assert get_stat_stage(unit.stat_boosts, "attack") == 0


def test_synchronize_mirrors_status_to_attacker(db, user):
    from app.routes.games import apply_status_effect

    ctx = _create_battle_game(db, user, link="synchronize")
    sync = _ability(
        db,
        name="Synchronize",
        slug="synchronize",
        effects=["on_statused:mirror_status:attacker"],
    )
    target = ctx["opponent_unit"]
    attacker = ctx["unit"]
    target.status_effects = []
    attacker.status_effects = []
    _attach_ability(target, sync, db)
    db.commit()

    applied = apply_status_effect(target, "paralysis", db, source=attacker)
    assert applied is True
    assert target.status_effects and target.status_effects[0] == "paralysis"
    assert attacker.status_effects and attacker.status_effects[0] == "paralysis"


def test_shadow_tag_traps_adjacent_opponent(db, user):
    ctx = _create_battle_game(db, user, link="shadow-tag")
    tag = _ability(db, name="Shadow Tag", slug="shadow_tag", effects=["trap_opponents"])
    trapper = ctx["opponent_unit"]
    victim = ctx["unit"]
    trapper.current_x, trapper.current_y = 2, 2
    victim.current_x, victim.current_y = 2, 3
    _attach_ability(trapper, tag, db)
    db.commit()

    assert ca.unit_traps_opponent(trapper, victim, db, get_types=get_unit_types) is True
    assert ca.is_trapped_by_adjacent_opponent(victim, db, get_types=get_unit_types) is True
