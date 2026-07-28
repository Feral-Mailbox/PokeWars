"""Gen 6 ability wiring tests for games.py + combat_abilities."""

import pytest

import app.db.models as models
from app import combat_abilities as ca
from app.routes.games import (
    apply_stat_change,
    consume_unit_held_item,
    get_stat_stage,
    set_unit_held_item,
    WEATHER_TO_ID,
)
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game


@pytest.fixture
def user(db):
    u = models.User(username="gen6-user", email="gen6@example.com", hashed_password="x")
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


def _ability(db, *, name, slug, effects, ability_id=None, generation=6):
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


def test_refrigerate_converts_normal_and_boosts(db, user):
    ctx = _create_battle_game(db, user, link="refrigerate")
    ab = _ability(
        db,
        name="Refrigerate",
        slug="refrigerate",
        effects=["convert_move_type:normal:to:ice", "on_converted_type:self:boost_power:1.2"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    normal = models.Move(name="Tackle", type="Normal", category="Physical", power=40, makes_contact=True)
    fire = models.Move(name="Ember", type="Fire", category="Special", power=40)
    assert ca.convert_move_type(attacker, normal, db) == "ice"
    assert ca.convert_move_type(attacker, fire, db) is None
    assert ca.attacker_power_multiplier(attacker, normal, db) == pytest.approx(1.2)
    assert ca.attacker_power_multiplier(attacker, fire, db) == 1.0


def test_tough_claws_boosts_contact(db, user):
    ctx = _create_battle_game(db, user, link="tough-claws")
    ab = _ability(
        db,
        name="Tough Claws",
        slug="tough_claws",
        effects=["on_move_flag:contact:self:boost_power:1.3"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    contact = models.Move(name="Tackle", type="Normal", category="Physical", power=40, makes_contact=True)
    ranged = models.Move(name="Swift", type="Normal", category="Special", power=60, makes_contact=False)
    assert ca.attacker_power_multiplier(attacker, contact, db) == pytest.approx(1.3)
    assert ca.attacker_power_multiplier(attacker, ranged, db) == 1.0


def test_fur_coat_halves_physical(db, user):
    ctx = _create_battle_game(db, user, link="fur-coat")
    ab = _ability(
        db,
        name="Fur Coat",
        slug="fur_coat",
        effects=["on_move_category:physical:self:resist:0.5"],
    )
    target = ctx["opponent_unit"]
    _attach_ability(target, ab, db)
    db.commit()

    physical = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    special = models.Move(name="Swift", type="Normal", category="Special", power=60)
    assert ca.defender_damage_multiplier(target, physical, "normal", 1.0, db) == 0.5
    assert ca.defender_damage_multiplier(target, special, "normal", 1.0, db) == 1.0


def test_gooey_lowers_speed_on_contact(db, user):
    ctx = _create_battle_game(db, user, link="gooey")
    ab = _ability(
        db,
        name="Gooey",
        slug="gooey",
        effects=["on_contact:attacker:lower_stat:speed:1"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.stat_boosts = {}
    _attach_ability(defender, ab, db)
    db.commit()

    from app.routes.games import apply_stat_change as asc

    msgs = ca.process_contact_abilities(
        attacker,
        defender,
        makes_contact=True,
        damage=10,
        db=db,
        helpers={"apply_stat_change": asc, "current_turn": 1},
    )
    assert msgs
    assert get_stat_stage(attacker.stat_boosts, "speed") == -1


def test_competitive_raises_spa_when_attack_lowered(db, user):
    ctx = _create_battle_game(db, user, link="competitive")
    ab = _ability(
        db,
        name="Competitive",
        slug="competitive",
        effects=["on_stat_lowered_by_opponent:self:raise_stat:special_attack:2"],
    )
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, ab, db)
    db.commit()

    apply_stat_change(unit, "attack", -1, 1, db, from_opponent=True)
    assert get_stat_stage(unit.stat_boosts, "attack") == -1
    assert get_stat_stage(unit.stat_boosts, "sp_attack") == 2


def test_dark_aura_boosts_and_aura_break_reverses(db, user):
    ctx = _create_battle_game(db, user, link="dark-aura")
    dark = _ability(
        db,
        name="Dark Aura",
        slug="dark_aura",
        effects=["field:on_move_type:dark:boost_power:1.33"],
    )
    holder = ctx["unit"]
    _attach_ability(holder, dark, db)
    db.commit()

    assert ca.field_move_type_power_multiplier(ctx["game"].id, "dark", db) == pytest.approx(1.33)
    assert ca.field_move_type_power_multiplier(ctx["game"].id, "fairy", db) == 1.0

    brk = _ability(
        db,
        name="Aura Break",
        slug="aura_break",
        effects=["reverse_aura_abilities"],
    )
    opp = ctx["opponent_unit"]
    _attach_ability(opp, brk, db)
    db.commit()

    assert ca.field_move_type_power_multiplier(ctx["game"].id, "dark", db) == pytest.approx(1.0 / 1.33)


def test_sweet_veil_blocks_ally_sleep(db, user):
    ctx = _create_battle_game(db, user, link="sweet-veil")
    veil = _ability(
        db,
        name="Sweet Veil",
        slug="sweet_veil",
        effects=["self_and_allies:immune_status:sleep"],
    )
    holder = ctx["unit"]
    _attach_ability(holder, veil, db)

    ally = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=user.id,
        unit_id=holder.unit_id,
        level=holder.level,
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
    db.add(ally)
    db.flush()
    db.commit()

    assert ca.can_apply_status(ally, "sleep", db) is False
    assert ca.can_apply_status(ally, "burn", db) is True


def test_grass_pelt_boosts_def_on_grassy(db, user):
    ctx = _create_battle_game(db, user, link="grass-pelt")
    ab = _ability(
        db,
        name="Grass Pelt",
        slug="grass_pelt",
        effects=["on_terrain:grassy:self:boost_stat_mult:defense:1.5"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    base = {"hp": 100, "attack": 50, "defense": 100, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    grassy = [[[3, 5] for _ in range(6)] for _ in range(6)]
    out = ca.modify_effective_stats(unit, base, db, terrain_tiles=grassy)
    assert out["defense"] == 150
    out_clear = ca.modify_effective_stats(unit, base, db, terrain_tiles=None)
    assert out_clear["defense"] == 100


def test_bulletproof_blocks_ball_bomb(db, user):
    ctx = _create_battle_game(db, user, link="bulletproof")
    ab = _ability(
        db,
        name="Bulletproof",
        slug="bulletproof",
        effects=["immune_category:ball_bomb"],
    )
    target = ctx["opponent_unit"]
    _attach_ability(target, ab, db)
    db.commit()

    sludge = models.Move(name="Sludge Bomb", type="Poison", category="Special", power=90)
    shadow = models.Move(name="Shadow Ball", type="Ghost", category="Special", power=80)
    tackle = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.blocks_ball_bomb_move(target, sludge, db) is True
    assert ca.blocks_ball_bomb_move(target, shadow, db) is True
    assert ca.blocks_ball_bomb_move(target, tackle, db) is False
    assert ca.should_block_move_against(target, sludge, db) == "bulletproof"


def test_parental_bond_second_hit_power(db, user):
    ctx = _create_battle_game(db, user, link="parental-bond")
    ab = _ability(
        db,
        name="Parental Bond",
        slug="parental_bond",
        effects=["multi_hit:2", "second_hit_power:0.25"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.parental_bond_hit_count(attacker, move, db) == 2
    assert ca.parental_bond_hit_power_mult(0) == 1.0
    assert ca.parental_bond_hit_power_mult(1) == 0.25


def test_cheek_pouch_heals_on_berry_consume(db, user):
    ctx = _create_battle_game(db, user, link="cheek-pouch")
    ab = _ability(
        db,
        name="Cheek Pouch",
        slug="cheek_pouch",
        effects=["on_berry_eat:self:heal_fraction:3"],
    )
    unit = ctx["unit"]
    unit.current_stats = {**(unit.current_stats or {}), "hp": 90}
    unit.current_hp = 30
    set_unit_held_item(unit, "oran_berry", db)
    _attach_ability(unit, ab, db)
    db.commit()

    assert consume_unit_held_item(unit, db, item_type="berry") is True
    assert unit.current_hp == 60  # 30 + 90/3


def test_magician_steals_item_on_damage(db, user):
    ctx = _create_battle_game(db, user, link="magician")
    ab = _ability(
        db,
        name="Magician",
        slug="magician",
        effects=["on_damage_dealt:self:steal_item"],
    )
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    set_unit_held_item(target, "leftovers", db)
    _attach_ability(attacker, ab, db)
    db.commit()

    from app.routes.games import get_unit_held_item

    msgs = ca.process_magician_steal(
        attacker,
        target,
        20,
        db,
        helpers={"get_unit_held_item": get_unit_held_item, "set_unit_held_item": set_unit_held_item},
    )
    assert msgs
    assert get_unit_held_item(attacker) == "leftovers"
    assert get_unit_held_item(target) is None


def test_protean_changes_type_once(db, user):
    ctx = _create_battle_game(db, user, link="protean")
    ab = _ability(
        db,
        name="Protean",
        slug="protean",
        effects=["on_move_use:self:change_type:move_type:once_per_switch_in"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    assert ca.process_protean(unit, "water", db) is True
    assert ca.get_battle_types(unit, db) == {"water"}
    assert ca.process_protean(unit, "fire", db) is False
    assert ca.get_battle_types(unit, db) == {"water"}

    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=None,
        map_state=None,
        current_turn=1,
    )
    assert (unit.flags or {}).get("protean_used") is None
    assert ca.process_protean(unit, "grass", db) is True


def test_primordial_sea_nullifies_fire(db, user):
    assert ca.move_type_nullified_by_weather("fire", WEATHER_TO_ID["heavy_rain"]) is True
    assert ca.move_type_nullified_by_weather("water", WEATHER_TO_ID["heavy_rain"]) is False
    assert ca.move_type_nullified_by_weather("water", WEATHER_TO_ID["harsh_sun"]) is True
    assert ca.move_type_nullified_by_weather("fire", WEATHER_TO_ID["harsh_sun"]) is False

    ctx = _create_battle_game(db, user, link="primordial-sea")
    ab = _ability(
        db,
        name="Primordial Sea",
        slug="primordial_sea",
        effects=["on_switch_in:weather:heavy_rain", "nullify_move_type:fire"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    map_state = db.query(models.GameMapState).filter_by(game_id=ctx["game"].id).first()
    assert map_state is not None
    db.commit()

    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=None,
        map_state=map_state,
        current_turn=1,
        helpers={"WEATHER_TO_ID": WEATHER_TO_ID},
    )
    wid = map_state.weather_tiles[0][0] if map_state.weather_tiles else 0
    assert wid == WEATHER_TO_ID["heavy_rain"]


def test_flower_veil_blocks_grass_ally_status(db, user):
    ctx = _create_battle_game(db, user, link="flower-veil")
    veil = _ability(
        db,
        name="Flower Veil",
        slug="flower_veil",
        effects=["grass_allies:immune_status:all", "grass_allies:immune_stat_drop"],
    )
    holder = ctx["unit"]
    _attach_ability(holder, veil, db)

    # Make an ally with grass battle type
    ally = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=user.id,
        unit_id=holder.unit_id,
        level=holder.level,
        starting_x=3,
        starting_y=3,
        current_x=3,
        current_y=3,
        current_hp=100,
        current_stats={"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50},
        is_fainted=False,
        can_move=True,
        flags={"battle_types": ["grass"]},
        stat_boosts={},
        status_effects=[],
        states=[],
        move_pp=[5, 5, 5, 5],
    )
    db.add(ally)
    db.flush()
    db.commit()

    assert ca.can_apply_status(ally, "poison", db) is False
    assert ca.blocks_stat_drop(ally, "attack", db, from_opponent=True) is True


def test_strong_jaw_and_mega_launcher(db, user):
    ctx = _create_battle_game(db, user, link="jaw-launcher")
    jaw = _ability(
        db,
        name="Strong Jaw",
        slug="strong_jaw",
        effects=["on_move_flag:bite:self:boost_power:1.5"],
    )
    launch = _ability(
        db,
        name="Mega Launcher",
        slug="mega_launcher",
        effects=["on_move_flag:pulse:self:boost_power:1.5"],
    )
    a = ctx["unit"]
    _attach_ability(a, jaw, db)
    db.commit()
    crunch = models.Move(name="Crunch", type="Dark", category="Physical", power=80)
    assert ca.attacker_power_multiplier(a, crunch, db) == pytest.approx(1.5)

    _attach_ability(a, launch, db)
    db.commit()
    pulse = models.Move(name="Dark Pulse", type="Dark", category="Special", power=80)
    assert ca.attacker_power_multiplier(a, pulse, db) == pytest.approx(1.5)


def test_gale_wings_priority_helper(db, user):
    ctx = _create_battle_game(db, user, link="gale-wings")
    ab = _ability(
        db,
        name="Gale Wings",
        slug="gale_wings",
        effects=["on_hp_full:on_move_type:flying:priority:1"],
    )
    unit = ctx["unit"]
    max_hp = int((unit.current_stats or {}).get("hp") or 100)
    unit.current_stats = {**(unit.current_stats or {}), "hp": max_hp}
    unit.current_hp = max_hp
    _attach_ability(unit, ab, db)
    db.commit()

    flying = models.Move(name="Air Slash", type="Flying", category="Special", power=75)
    assert ca.flying_move_priority_bonus(unit, flying, db) == 1
    unit.current_hp = max(1, max_hp // 2)
    assert ca.flying_move_priority_bonus(unit, flying, db) == 0
