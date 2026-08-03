"""Tests for newly wired unit volatile states."""

import pytest

import app.db.models as models
from app.routes import games as games_module
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game


@pytest.fixture
def user(db):
    u = models.User(username="state-user", email="state@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_state_aliases_normalize(db, user):
    assert games_module.canonical_state_name("disabled") == "disable"
    assert games_module.canonical_state_name("curse") == "cursed"
    assert games_module.canonical_state_name("perish_song") == "perish"
    assert games_module.normalize_states(["disabled", 3]) == ["disable", 3]


def test_apply_protect_and_recharge(db, user):
    ctx = _create_battle_game(db, user, link="protect-state")
    unit = ctx["unit"]
    unit.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    unit.current_hp = 100
    db.add(unit)
    db.commit()

    assert games_module.apply_state_effect(unit, "protect", db) is True
    assert games_module.unit_is_protected(unit) is True

    unit.states = []
    assert games_module.apply_state_effect(unit, "recharge", db) is True
    assert games_module.normalize_states(unit.states)[0] == "recharge"


def test_substitute_absorbs_damage(db, user):
    ctx = _create_battle_game(db, user, link="sub-state")
    unit = ctx["unit"]
    attacker = ctx["opponent_unit"]
    unit.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    unit.current_hp = 100
    db.add(unit)
    db.commit()

    assert games_module.apply_state_effect(unit, "substitute", db) is True
    assert unit.current_hp == 75
    assert games_module.get_unit_flags(unit).get("substitute_hp") == 25

    remaining = games_module.absorb_damage_with_substitute(unit, 10, attacker, db)
    assert remaining == 0
    assert games_module.get_unit_flags(unit).get("substitute_hp") == 15
    assert unit.current_hp == 75


def test_leech_seed_and_trap_apply(db, user):
    ctx = _create_battle_game(db, user, link="seed-trap")
    unit = ctx["opponent_unit"]
    unit.current_stats = {"hp": 80, "attack": 40, "defense": 40, "sp_attack": 40, "sp_defense": 40, "speed": 40}
    unit.current_hp = 80
    db.add(unit)
    db.commit()

    assert games_module.apply_state_effect(unit, "leech_seed", db) is True
    assert games_module.normalize_states(unit.states)[0] == "leech_seed"

    unit.states = []
    assert games_module.apply_state_effect(unit, "trap", db) is True
    assert games_module.normalize_states(unit.states)[0] == "trap"


def test_foresight_and_power_trick_apply(db, user):
    ctx = _create_battle_game(db, user, link="foresight-pt")
    unit = ctx["unit"]
    unit.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    unit.current_hp = 100
    db.add(unit)
    db.commit()

    assert games_module.apply_state_effect(unit, "foresight", db) is True
    assert games_module.normalize_states(unit.states) == ["foresight", games_module.SCREEN_EFFECT_DURATION]

    unit.states = []
    assert games_module.apply_state_effect(unit, "power_trick", db) is True
    assert games_module.normalize_states(unit.states)[0] == "power_trick"
    # Toggle off
    assert games_module.apply_state_effect(unit, "power_trick", db) is True
    assert games_module.normalize_states(unit.states) == []


def test_move_charge_state_detection():
    dig = models.Move(name="Dig", effects=["delayed_hit:1", "self:apply_state:underground"])
    assert games_module.move_charge_state(dig) == "underground"
    solar = models.Move(name="Solar Beam", effects=["self:apply_state:solar_beam"])
    assert games_module.move_charge_state(solar) == "solar_beam"
