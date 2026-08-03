"""Tests for ability trigger chat / system_log announcements."""

import pytest

import app.db.models as models
from app import combat_abilities as ca
from app.routes.games import get_unit_display_name
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game


def _ability(db, *, name, slug, effects, ability_id=None, generation=3):
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


@pytest.fixture
def user(db):
    u = models.User(username="ability-chat-user", email="ability-chat@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def test_ability_protect_message_bulletproof(db, user):
    ctx = _create_battle_game(db, user, link="bp-chat")
    ab = _ability(db, name="Bulletproof", slug="bulletproof", effects=["immune_category:ball_bomb"])
    target = ctx["opponent_unit"]
    _attach_ability(target, ab, db)
    db.commit()

    move = models.Move(name="Sludge Bomb", type="Poison", category="Special", power=90, move_trait=8)
    db.add(move)
    db.commit()

    msg = ca.ability_protect_message(target, move, db, unit_name="Foe's Golem")
    assert msg == "Foe's Golem is protected by Bulletproof!"


def test_swift_swim_announces_once_in_rain(db, user):
    ctx = _create_battle_game(db, user, link="swift-chat")
    ab = _ability(
        db,
        name="Swift Swim",
        slug="swift_swim",
        effects=["on_weather:rain:self:boost_stat_mult:speed:2"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    unit.current_x = 1
    unit.current_y = 1
    unit.current_stats = {
        "hp": 100,
        "attack": 50,
        "defense": 50,
        "sp_attack": 50,
        "sp_defense": 50,
        "speed": 60,
    }
    db.add(unit)
    db.commit()

    weather = [[0, 0], [0, 2]]  # rain id 2 at (1,1)
    map_state = db.query(models.GameMapState).filter_by(game_id=ctx["game"].id).first()
    if map_state and isinstance(map_state.weather_tiles, list) and map_state.weather_tiles:
        h = len(map_state.weather_tiles)
        w = len(map_state.weather_tiles[0]) if h else 0
        weather = [[0 for _ in range(w)] for _ in range(h)]
        x, y = int(unit.current_x), int(unit.current_y)
        if 0 <= y < h and 0 <= x < w:
            weather[y][x] = 2

    msgs: list[str] = []
    name = get_unit_display_name(unit, db)
    out = ca.modify_effective_stats(
        unit,
        dict(unit.current_stats),
        db,
        weather_tiles=weather,
        trigger_messages=msgs,
        unit_name=name,
    )
    assert out["speed"] == 120
    assert any("Swift Swim" in m and "Speed" in m for m in msgs)

    msgs2: list[str] = []
    ca.modify_effective_stats(
        unit,
        dict(unit.current_stats),
        db,
        weather_tiles=weather,
        trigger_messages=msgs2,
        unit_name=name,
    )
    assert msgs2 == []


def test_iron_fist_announces_power_boost(db, user):
    ctx = _create_battle_game(db, user, link="fist-chat")
    ab = _ability(
        db,
        name="Iron Fist",
        slug="iron_fist",
        effects=["on_move_flag:punch:self:boost_power:1.2"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    punch = models.Move(
        name="Mach Punch",
        type="Fighting",
        category="Physical",
        power=40,
        move_trait=5,
    )
    db.add(punch)
    db.commit()

    msgs: list[str] = []
    mult = ca.attacker_power_multiplier(
        attacker,
        punch,
        db,
        trigger_messages=msgs,
        unit_name="Ash's Hitmonchan",
    )
    assert mult == pytest.approx(1.2)
    assert msgs == ["Ash's Hitmonchan's Iron Fist boosted the attack!"]
