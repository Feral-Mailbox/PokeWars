"""Gen 5 ability wiring tests for games.py + combat_abilities."""

import pytest

import app.db.models as models
from app import combat_abilities as ca
from app.routes.games import (
    apply_end_of_round_weather_damage,
    apply_stat_change,
    get_stat_stage,
    process_move_effects,
    WEATHER_TO_ID,
)
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game


@pytest.fixture
def user(db):
    u = models.User(username="gen5-user", email="gen5@example.com", hashed_password="x")
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


def _ability(db, *, name, slug, effects, ability_id=None, generation=5):
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


def test_sand_force_boosts_rock_in_sand(db, user):
    ctx = _create_battle_game(db, user, link="sand-force")
    sf = _ability(
        db,
        name="Sand Force",
        slug="sand_force",
        effects=[
            "on_weather:sandstorm:on_move_type:rock:self:boost_power:1.3",
            "on_weather:sandstorm:on_move_type:ground:self:boost_power:1.3",
            "on_weather:sandstorm:on_move_type:steel:self:boost_power:1.3",
        ],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, sf, db)
    w = WEATHER_TO_ID["sandstorm"]
    weather_tiles = [[w for _ in range(6)] for _ in range(6)]
    db.commit()

    rock = models.Move(name="Rock Slide", type="Rock", category="Physical", power=75)
    fire = models.Move(name="Flamethrower", type="Fire", category="Special", power=90)
    assert ca.attacker_power_multiplier(attacker, rock, db, weather_tiles=weather_tiles) == 1.3
    assert ca.attacker_power_multiplier(attacker, fire, db, weather_tiles=weather_tiles) == 1.0
    assert ca.attacker_power_multiplier(attacker, rock, db, weather_tiles=None) == 1.0


def test_multiscale_halves_at_full_hp(db, user):
    ctx = _create_battle_game(db, user, link="multiscale")
    ms = _ability(db, name="Multiscale", slug="multiscale", effects=["on_hp_full:self:resist:0.5"])
    target = ctx["opponent_unit"]
    target.current_stats = {**(target.current_stats or {}), "hp": 100}
    target.current_hp = 100
    _attach_ability(target, ms, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.defender_damage_multiplier(target, move, "normal", 1.0, db) == 0.5
    target.current_hp = 50
    db.add(target)
    db.flush()
    assert ca.defender_damage_multiplier(target, move, "normal", 1.0, db) == 1.0


def test_friend_guard_reduces_ally_damage(db, user):
    ctx = _create_battle_game(db, user, link="friend-guard")
    fg = _ability(db, name="Friend Guard", slug="friend_guard", effects=["allies:resist_damage:0.75"])
    # Put Friend Guard on an ally of the protected unit (same user)
    ally = ctx["unit"]
    _attach_ability(ally, fg, db)

    protected = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=user.id,
        unit_id=ally.unit_id,
        level=ally.level,
        starting_x=2,
        starting_y=2,
        current_x=2,
        current_y=2,
        current_hp=100,
        current_stats={"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50},
        is_fainted=False,
        can_move=True,
        flags={},
        stat_boosts={},
        status_effects=[],
        states=[],
        move_pp=[5, 5, 5, 5],
    )
    db.add(protected)
    db.flush()
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.defender_damage_multiplier(protected, move, "normal", 1.0, db) == 0.75


def test_defeatist_halves_atk_at_low_hp(db, user):
    ctx = _create_battle_game(db, user, link="defeatist")
    df = _ability(
        db,
        name="Defeatist",
        slug="defeatist",
        effects=[
            "on_hp_below:50:self:boost_stat_mult:attack:0.5",
            "on_hp_below:50:self:boost_stat_mult:special_attack:0.5",
        ],
    )
    unit = ctx["unit"]
    unit.current_stats = {
        **(unit.current_stats or {}),
        "hp": 100,
        "attack": 100,
        "sp_attack": 80,
    }
    unit.current_hp = 40
    _attach_ability(unit, df, db)
    db.commit()

    stats = ca.modify_effective_stats(unit, dict(unit.current_stats), db)
    assert stats["attack"] == 50
    assert stats["sp_attack"] == 40


def test_sheer_force_boosts_and_strips_secondary(db, user):
    ctx = _create_battle_game(db, user, link="sheer-force")
    sf = _ability(
        db,
        name="Sheer Force",
        slug="sheer_force",
        effects=["remove_secondary_effects", "on_moves_with_secondary:self:boost_power:1.3"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, sf, db)
    db.commit()

    with_sec = models.Move(
        name="Body Slam",
        type="Normal",
        category="Physical",
        power=85,
        effects=["target:status:paralysis:30"],
    )
    plain = models.Move(name="Strength", type="Normal", category="Physical", power=80, effects=[])
    assert ca.move_has_secondary_effects(with_sec) is True
    assert ca.removes_secondary_effects(attacker, db) is True
    assert ca.attacker_power_multiplier(attacker, with_sec, db) == 1.3
    assert ca.attacker_power_multiplier(attacker, plain, db) == 1.0


def test_moxie_on_ko(db, user):
    ctx = _create_battle_game(db, user, link="moxie")
    mx = _ability(db, name="Moxie", slug="moxie", effects=["on_ko:self:raise_stat:attack:1"])
    attacker = ctx["unit"]
    fainted = ctx["opponent_unit"]
    attacker.stat_boosts = {}
    _attach_ability(attacker, mx, db)
    db.commit()

    msgs = ca.process_on_ko(
        attacker,
        fainted,
        db,
        1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(attacker.stat_boosts, "attack") == 1


def test_justified_raises_atk_on_dark_hit(db, user):
    ctx = _create_battle_game(db, user, link="justified")
    ju = _ability(
        db,
        name="Justified",
        slug="justified",
        effects=["on_hit_type:dark:self:raise_stat:attack:1"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    defender.stat_boosts = {}
    _attach_ability(defender, ju, db)
    db.commit()

    move = models.Move(name="Dark Pulse", type="Dark", category="Special", power=80)
    msgs = ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=20,
        move_type="dark",
        is_physical=False,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(defender.stat_boosts, "attack") == 1


def test_weak_armor_on_physical(db, user):
    ctx = _create_battle_game(db, user, link="weak-armor")
    wa = _ability(
        db,
        name="Weak Armor",
        slug="weak_armor",
        effects=[
            "on_hit_category:physical:self:lower_stat:defense:1",
            "on_hit_category:physical:self:raise_stat:speed:2",
        ],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    defender.stat_boosts = {}
    _attach_ability(defender, wa, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=10,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert get_stat_stage(defender.stat_boosts, "defense") == -1
    assert get_stat_stage(defender.stat_boosts, "speed") == 2


def test_contrary_reverses_stat_change(db, user):
    ctx = _create_battle_game(db, user, link="contrary")
    ct = _ability(db, name="Contrary", slug="contrary", effects=["reverse_stat_changes"])
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, ct, db)
    db.commit()

    assert ca.reverse_stat_changes(unit, db) is True
    apply_stat_change(unit, "attack", -1, 1, db)
    assert get_stat_stage(unit.stat_boosts, "attack") == 1


def test_defiant_raises_atk_when_lowered(db, user):
    ctx = _create_battle_game(db, user, link="defiant")
    df = _ability(
        db,
        name="Defiant",
        slug="defiant",
        effects=["on_stat_lowered_by_opponent:self:raise_stat:attack:2"],
    )
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, df, db)
    db.commit()

    apply_stat_change(unit, "defense", -1, 1, db, from_opponent=True)
    assert get_stat_stage(unit.stat_boosts, "defense") == -1
    assert get_stat_stage(unit.stat_boosts, "attack") == 2


def test_mummy_sets_attacker_ability(db, user):
    ctx = _create_battle_game(db, user, link="mummy")
    mummy = _ability(
        db,
        name="Mummy",
        slug="mummy",
        effects=["on_contact:attacker:set_ability:mummy"],
    )
    other = _ability(db, name="Blaze", slug="blaze", effects=["on_hp_below:33:on_move_type:fire:self:boost_power:1.5"])
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    _attach_ability(defender, mummy, db)
    _attach_ability(attacker, other, db)
    db.commit()

    msgs = ca.process_contact_abilities(
        attacker,
        defender,
        makes_contact=True,
        damage=10,
        db=db,
    )
    assert msgs
    db.flush()
    db.refresh(attacker)
    assert int((attacker.flags or {}).get("ability_id")) == mummy.id


def test_poison_touch_poisons_on_contact(db, user, monkeypatch):
    ctx = _create_battle_game(db, user, link="poison-touch")
    pt = _ability(
        db,
        name="Poison Touch",
        slug="poison_touch",
        effects=["on_contact_deal:target:status:poison:30"],
    )
    attacker = ctx["unit"]
    defender = ctx["opponent_unit"]
    defender.status_effects = []
    _attach_ability(attacker, pt, db)
    db.commit()

    monkeypatch.setattr(ca.random, "randint", lambda a, b: 1)
    msgs = ca.process_attacker_contact_on_hit(
        attacker,
        defender,
        makes_contact=True,
        damage=10,
        db=db,
    )
    assert msgs
    db.flush()
    db.refresh(defender)
    assert defender.status_effects and defender.status_effects[0] == "poison"


def test_overcoat_blocks_weather_chip(db, user):
    ctx = _create_battle_game(db, user, link="overcoat")
    oc = _ability(
        db,
        name="Overcoat",
        slug="overcoat",
        effects=["immune_weather_damage", "immune_category:powder"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, oc, db)

    map_state = ctx["map_state"]
    w = WEATHER_TO_ID["sandstorm"]
    map_state.weather_tiles = [[w for _ in range(6)] for _ in range(6)]
    db.add(map_state)

    unit.current_stats = {**(unit.current_stats or {}), "hp": 100}
    unit.current_hp = 100
    # Make unit not rock/ground/steel so sand would normally chip
    flags = dict(unit.flags or {})
    flags["battle_types"] = ["normal"]
    unit.flags = flags

    opp = ctx["opponent_unit"]
    opp.current_stats = {**(opp.current_stats or {}), "hp": 100}
    opp.current_hp = 100
    opp_flags = dict(opp.flags or {})
    opp_flags["battle_types"] = ["normal"]
    opp.flags = opp_flags
    db.commit()

    assert ca.should_ignore_weather_damage(unit, db) is True
    modified = apply_end_of_round_weather_damage(ctx["game"].id, db)
    db.flush()
    db.refresh(unit)
    db.refresh(opp)
    assert unit.current_hp == 100
    assert opp.current_hp < 100
    assert unit.id not in modified


def test_moody_changes_stats(db, user, monkeypatch):
    ctx = _create_battle_game(db, user, link="moody")
    moody = _ability(
        db,
        name="Moody",
        slug="moody",
        effects=[
            "on_turn_end:self:raise_random_stat:2",
            "on_turn_end:self:lower_other_random_stat:1",
        ],
    )
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, moody, db)
    db.commit()

    choices = iter(["attack", "speed"])
    monkeypatch.setattr(ca.random, "choice", lambda seq: next(choices))

    ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        weather_tiles=None,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    db.flush()
    db.refresh(unit)
    assert get_stat_stage(unit.stat_boosts, "attack") == 2
    assert get_stat_stage(unit.stat_boosts, "speed") == -1


def test_telepathy_skips_ally_damage_path(db, user):
    ctx = _create_battle_game(db, user, link="telepathy")
    tp = _ability(db, name="Telepathy", slug="telepathy", effects=["immune_ally_attacks"])
    ally = ctx["unit"]
    _attach_ability(ally, tp, db)
    db.commit()

    assert ca.immune_to_ally_attacks(ally, db) is True
    assert ca.immune_to_ally_attacks(ctx["opponent_unit"], db) is False


def test_magic_bounce_reflects_status(db, user):
    ctx = _create_battle_game(db, user, link="magic-bounce")
    mb = _ability(db, name="Magic Bounce", slug="magic_bounce", effects=["reflect_status_moves"])
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.status_effects = []
    defender.status_effects = []
    _attach_ability(defender, mb, db)
    db.commit()

    assert ca.reflects_status_moves(defender, db) is True
    move = models.Move(
        name="Thunder Wave",
        type="Electric",
        category="Status",
        power=None,
        effects=["target:status:paralysis:100"],
    )
    process_move_effects(move, attacker, [defender], 1, db, game=ctx["game"], game_state=ctx["state"])
    db.flush()
    db.refresh(attacker)
    db.refresh(defender)
    # Bounced onto attacker
    assert attacker.status_effects and attacker.status_effects[0] == "paralysis"
    assert not defender.status_effects or defender.status_effects[0] != "paralysis"


def test_analytic_when_last_mover(db, user):
    ctx = _create_battle_game(db, user, link="analytic")
    an = _ability(db, name="Analytic", slug="analytic", effects=["on_move_last:self:boost_power:1.3"])
    attacker = ctx["unit"]
    _attach_ability(attacker, an, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(attacker, move, db, is_last_move=True) == 1.3
    assert ca.attacker_power_multiplier(attacker, move, db, is_last_move=False) == 1.0
    assert ca.attacker_power_multiplier(attacker, move, db, is_last_move=None) == 1.0


def test_harvest_restores_berry_in_sun(db, user, monkeypatch):
    ctx = _create_battle_game(db, user, link="harvest")
    hv = _ability(
        db,
        name="Harvest",
        slug="harvest",
        effects=[
            "on_turn_end:self:recycle_berry:50",
            "on_weather:sun:on_turn_end:self:recycle_berry:100",
        ],
    )
    unit = ctx["unit"]
    flags = dict(unit.flags or {})
    flags.pop("held_item", None)
    flags["consumed_berry"] = "oran-berry"
    unit.flags = flags
    _attach_ability(unit, hv, db)

    w = WEATHER_TO_ID["sun"]
    weather_tiles = [[w for _ in range(6)] for _ in range(6)]
    db.commit()

    # Force the 50% recycle to fail so sun's 100% path restores
    monkeypatch.setattr(ca.random, "randint", lambda a, b: 100)

    ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        weather_tiles=weather_tiles,
        current_turn=1,
    )
    db.flush()
    db.refresh(unit)
    assert (unit.flags or {}).get("held_item") == "oran-berry"


def test_flare_and_toxic_boost(db, user):
    ctx = _create_battle_game(db, user, link="flare-boost")
    flare = _ability(
        db,
        name="Flare Boost",
        slug="flare_boost",
        effects=["on_status:burn:on_move_category:special:self:boost_power:1.5"],
    )
    unit = ctx["unit"]
    unit.status_effects = ["burn", 5]
    _attach_ability(unit, flare, db)
    db.commit()
    special = models.Move(name="Flamethrower", type="Fire", category="Special", power=90)
    physical = models.Move(name="Flare Blitz", type="Fire", category="Physical", power=120)
    assert ca.attacker_power_multiplier(unit, special, db) == 1.5
    assert ca.attacker_power_multiplier(unit, physical, db) == 1.0

    ctx2 = _create_battle_game(db, user, link="toxic-boost")
    toxic = _ability(
        db,
        name="Toxic Boost",
        slug="toxic_boost",
        effects=[
            "on_status:poison:on_move_category:physical:self:boost_power:1.5",
            "on_status:badly_poison:on_move_category:physical:self:boost_power:1.5",
        ],
    )
    unit2 = ctx2["unit"]
    unit2.status_effects = ["poison", 5]
    _attach_ability(unit2, toxic, db)
    db.commit()
    assert ca.attacker_power_multiplier(unit2, physical, db) == 1.5
    assert ca.attacker_power_multiplier(unit2, special, db) == 1.0