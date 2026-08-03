"""Gen 7 ability wiring tests for games.py + combat_abilities."""

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
    u = models.User(username="gen7-user", email="gen7@example.com", hashed_password="x")
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


def _ability(db, *, name, slug, effects, ability_id=None, generation=7):
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


def test_steelworker_boosts_steel(db, user):
    ctx = _create_battle_game(db, user, link="steelworker")
    ab = _ability(
        db,
        name="Steelworker",
        slug="steelworker",
        effects=["on_move_type:steel:self:boost_power:1.5"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    steel = models.Move(name="Iron Head", type="Steel", category="Physical", power=80)
    normal = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(attacker, steel, db) == pytest.approx(1.5)
    assert ca.attacker_power_multiplier(attacker, normal, db) == 1.0


def test_water_bubble_water_power_fire_resist_burn_block(db, user):
    ctx = _create_battle_game(db, user, link="water-bubble")
    ab = _ability(
        db,
        name="Water Bubble",
        slug="water_bubble",
        effects=[
            "on_hit_type:fire:self:resist:0.5",
            "on_move_type:water:self:boost_power:2",
            "immune_status:burn",
        ],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    water = models.Move(name="Water Gun", type="Water", category="Special", power=40)
    fire = models.Move(name="Ember", type="Fire", category="Special", power=40)
    assert ca.attacker_power_multiplier(unit, water, db) == pytest.approx(2.0)
    assert ca.defender_damage_multiplier(unit, fire, "fire", 1.0, db) == 0.5
    assert ca.can_apply_status(unit, "burn", db) is False


def test_fluffy_halves_contact_doubles_fire(db, user):
    ctx = _create_battle_game(db, user, link="fluffy")
    ab = _ability(
        db,
        name="Fluffy",
        slug="fluffy",
        effects=["on_move_flag:contact:self:resist:0.5", "on_hit_type:fire:self:resist:2"],
    )
    target = ctx["opponent_unit"]
    _attach_ability(target, ab, db)
    db.commit()

    contact = models.Move(name="Tackle", type="Normal", category="Physical", power=40, makes_contact=True)
    fire = models.Move(name="Ember", type="Fire", category="Special", power=40, makes_contact=False)
    fire_contact = models.Move(
        name="Fire Punch", type="Fire", category="Physical", power=75, makes_contact=True
    )
    assert ca.defender_damage_multiplier(target, contact, "normal", 1.0, db) == 0.5
    assert ca.defender_damage_multiplier(target, fire, "fire", 1.0, db) == 2.0
    # Fire + contact → 0.5 * 2 = 1.0
    assert ca.defender_damage_multiplier(target, fire_contact, "fire", 1.0, db) == pytest.approx(1.0)


def test_galvanize_converts_normal_to_electric(db, user):
    ctx = _create_battle_game(db, user, link="galvanize")
    ab = _ability(
        db,
        name="Galvanize",
        slug="galvanize",
        effects=["convert_move_type:normal:to:electric", "on_converted_type:self:boost_power:1.2"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    normal = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    water = models.Move(name="Water Gun", type="Water", category="Special", power=40)
    assert ca.convert_move_type(attacker, normal, db) == "electric"
    assert ca.convert_move_type(attacker, water, db) is None
    assert ca.attacker_power_multiplier(attacker, normal, db) == pytest.approx(1.2)


def test_stamina_raises_def_on_hit(db, user):
    ctx = _create_battle_game(db, user, link="stamina")
    ab = _ability(
        db,
        name="Stamina",
        slug="stamina",
        effects=["on_damage_taken:self:raise_stat:defense:1"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    defender.stat_boosts = {}
    _attach_ability(defender, ab, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    msgs = ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=20,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(defender.stat_boosts, "defense") == 1


def test_beast_boost_raises_highest_on_ko(db, user):
    ctx = _create_battle_game(db, user, link="beast-boost")
    ab = _ability(
        db,
        name="Beast Boost",
        slug="beast_boost",
        effects=["on_ko:self:raise_stat:highest:1"],
    )
    attacker = ctx["unit"]
    fainted = ctx["opponent_unit"]
    attacker.stat_boosts = {}
    attacker.current_stats = {
        "hp": 100,
        "attack": 50,
        "defense": 40,
        "sp_attack": 80,
        "sp_defense": 40,
        "speed": 60,
    }
    _attach_ability(attacker, ab, db)
    db.commit()

    msgs = ca.process_on_ko(
        attacker,
        fainted,
        db,
        1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(attacker.stat_boosts, "sp_attack") == 1


def test_merciless_crits_poisoned_target(db, user):
    ctx = _create_battle_game(db, user, link="merciless")
    ab = _ability(
        db,
        name="Merciless",
        slug="merciless",
        effects=[
            "on_target_status:poison:guaranteed_crit",
            "on_target_status:badly_poison:guaranteed_crit",
        ],
    )
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    _attach_ability(attacker, ab, db)
    target.status_effects = ["poison", 3]
    db.commit()

    assert ca.guaranteed_crit_vs(attacker, target, db) is True
    target.status_effects = []
    assert ca.guaranteed_crit_vs(attacker, target, db) is False


def test_long_reach_removes_contact(db, user):
    ctx = _create_battle_game(db, user, link="long-reach")
    long_reach = _ability(
        db,
        name="Long Reach",
        slug="long_reach",
        effects=["remove_contact_flag"],
    )
    gooey = _ability(
        db,
        name="Gooey",
        slug="gooey",
        effects=["on_contact:attacker:lower_stat:speed:1"],
        generation=6,
    )
    attacker = ctx["unit"]
    defender = ctx["opponent_unit"]
    attacker.stat_boosts = {}
    _attach_ability(attacker, long_reach, db)
    _attach_ability(defender, gooey, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40, makes_contact=True)
    assert ca.move_makes_contact(attacker, move, db) is False
    msgs = ca.process_contact_abilities(
        attacker,
        defender,
        makes_contact=ca.move_makes_contact(attacker, move, db),
        damage=10,
        db=db,
        helpers={"apply_stat_change": apply_stat_change, "current_turn": 1},
    )
    assert msgs == []
    assert get_stat_stage(attacker.stat_boosts, "speed") == 0


def test_electric_surge_sets_terrain(db, user):
    ctx = _create_battle_game(db, user, link="electric-surge")
    ab = _ability(
        db,
        name="Electric Surge",
        slug="electric_surge",
        effects=["on_switch_in:terrain:electric"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    map_state = ctx["map_state"]
    # Ensure terrain grid exists
    h = len(map_state.weather_tiles or [[0]])
    w = len((map_state.weather_tiles or [[0]])[0])
    map_state.terrain_effect_tiles = [[[0, 0] for _ in range(w)] for _ in range(h)]
    db.add(map_state)
    db.commit()

    msgs = ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=map_state,
        current_turn=1,
        helpers={"TERRAIN_TO_ID": TERRAIN_TO_ID},
    )
    assert any("electric" in m.lower() for m in msgs)
    cell = map_state.terrain_effect_tiles[0][0]
    assert int(cell[0]) == TERRAIN_TO_ID["electric"]
    assert int(cell[1]) == 5


def test_surge_surfer_doubles_speed_on_electric_terrain(db, user):
    ctx = _create_battle_game(db, user, link="surge-surfer")
    ab = _ability(
        db,
        name="Surge Surfer",
        slug="surge_surfer",
        effects=["on_terrain:electric:self:boost_stat_mult:speed:2"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    stats = {"speed": 50, "attack": 40}
    terrain = [[[TERRAIN_TO_ID["electric"], 5]]]
    unit.current_x = 0
    unit.current_y = 0
    boosted = ca.modify_effective_stats(unit, stats, db, terrain_tiles=terrain)
    assert boosted["speed"] == 100


def test_neuroforce_boosts_se(db, user):
    ctx = _create_battle_game(db, user, link="neuroforce")
    ab = _ability(
        db,
        name="Neuroforce",
        slug="neuroforce",
        effects=["on_super_effective_deal:self:boost_power:1.25"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    move = models.Move(name="Hyper Beam", type="Normal", category="Special", power=150)
    assert ca.neuroforce_power_multiplier(attacker, 2.0, db) == pytest.approx(1.25)
    assert ca.neuroforce_power_multiplier(attacker, 1.0, db) == 1.0
    assert ca.attacker_power_multiplier(attacker, move, db, type_multiplier=2.0) == pytest.approx(1.25)


def test_soul_heart_on_any_faint(db, user):
    ctx = _create_battle_game(db, user, link="soul-heart")
    ab = _ability(
        db,
        name="Soul-Heart",
        slug="soul_heart",
        effects=["on_any_faint:self:raise_stat:special_attack:1"],
    )
    holder = ctx["unit"]
    fainted = ctx["opponent_unit"]
    holder.stat_boosts = {}
    _attach_ability(holder, ab, db)
    db.commit()

    msgs = ca.process_any_faint(
        fainted,
        [holder, fainted],
        db,
        1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(holder.stat_boosts, "sp_attack") == 1

    # Does not trigger for the Soul-Heart holder fainting itself
    holder.stat_boosts = {}
    msgs2 = ca.process_any_faint(
        holder,
        [holder],
        db,
        1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs2 == []
    assert get_stat_stage(holder.stat_boosts, "sp_attack") == 0


def test_disguise_blocks_first_hit(db, user):
    ctx = _create_battle_game(db, user, link="disguise")
    ab = _ability(
        db,
        name="Disguise",
        slug="disguise",
        effects=[
            "on_first_hit:block_damage",
            "on_disguise_break:self:damage_fraction:8",
            "change_forme:busted",
        ],
    )
    defender = ctx["opponent_unit"]
    defender.current_stats = dict(defender.current_stats or {})
    defender.current_stats["hp"] = 80
    defender.current_hp = 80
    _attach_ability(defender, ab, db)
    db.commit()

    chip, msgs = ca.apply_disguise(defender, 50, db)
    assert chip == 10  # 80 / 8
    assert msgs
    assert (defender.flags or {}).get("disguise_busted") is True
    assert (defender.flags or {}).get("forme") == "busted"

    # Second hit is not blocked
    chip2, msgs2 = ca.apply_disguise(defender, 50, db)
    assert chip2 == 50
    assert msgs2 == []


def test_battery_boosts_ally_special(db, user):
    ctx = _create_battle_game(db, user, link="battery")
    battery = _ability(
        db,
        name="Battery",
        slug="battery",
        effects=["allies:on_move_category:special:boost_power:1.3"],
    )
    # Attach Battery to opponent as "ally" of a second unit on same side — use user's unit as attacker
    # and put Battery on a second ally. _create_battle_game only has one unit per side, so
    # clone flags onto a temporary ally by querying and attaching Battery to a helper unit.
    attacker = ctx["unit"]
    # Create an ally GameUnit sharing user_id
    ally = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=attacker.user_id,
        unit_id=attacker.unit_id,
        level=attacker.level,
        current_hp=50,
        starting_x=0,
        starting_y=1,
        current_x=0,
        current_y=1,
        current_stats=dict(attacker.current_stats or {}),
        is_fainted=False,
        can_move=True,
        flags={},
        move_pp=[],
        status_effects=[],
        states=[],
        stat_boosts={},
    )
    db.add(ally)
    db.flush()
    _attach_ability(ally, battery, db)
    db.commit()

    special = models.Move(name="Swift", type="Normal", category="Special", power=60)
    physical = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(attacker, special, db) == pytest.approx(1.3)
    assert ca.attacker_power_multiplier(attacker, physical, db) == 1.0


def test_liquid_voice_makes_sound_moves_water(db, user):
    ctx = _create_battle_game(db, user, link="liquid-voice")
    ab = _ability(
        db,
        name="Liquid Voice",
        slug="liquid_voice",
        effects=["convert_move_category:sound:to_type:water"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    sound = models.Move(
        name="Hyper Voice", type="Normal", category="Special", power=90, move_trait=1
    )
    quiet = models.Move(name="Tackle", type="Normal", category="Physical", power=40, move_trait=0)
    assert ca.convert_move_type(attacker, sound, db) == "water"
    assert ca.convert_move_type(attacker, quiet, db) is None


def test_corrosion_can_poison_steel(db, user):
    ctx = _create_battle_game(db, user, link="corrosion")
    ab = _ability(
        db,
        name="Corrosion",
        slug="corrosion",
        effects=["can_poison:steel", "can_poison:poison"],
    )
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    _attach_ability(attacker, ab, db)
    # Force steel typing via battle_types flag
    flags = dict(target.flags or {})
    flags["battle_types"] = ["steel"]
    target.flags = flags
    db.add(target)
    db.commit()

    assert ca.can_poison_target(attacker, target, db) is True
    applied = apply_status_effect(target, "poison", db, source=attacker)
    assert applied is True
    assert target.status_effects[0] == "poison"


def test_innards_out_damages_attacker_on_faint(db, user):
    ctx = _create_battle_game(db, user, link="innards-out")
    ab = _ability(
        db,
        name="Innards Out",
        slug="innards_out",
        effects=["on_faint_from_move:attacker:damage_equal_to_hp_lost"],
    )
    fainted = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.current_hp = 100
    attacker.current_stats = dict(attacker.current_stats or {})
    attacker.current_stats["hp"] = 100
    _attach_ability(fainted, ab, db)
    db.commit()

    msgs = ca.process_innards_out(fainted, attacker, hp_lost=42, db=db)
    assert msgs
    assert attacker.current_hp == 58


def test_berserk_crosses_50(db, user):
    ctx = _create_battle_game(db, user, link="berserk")
    ab = _ability(
        db,
        name="Berserk",
        slug="berserk",
        effects=["on_hp_cross_below:50:self:raise_stat:special_attack:1"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    defender.stat_boosts = {}
    defender.current_stats = dict(defender.current_stats or {})
    defender.current_stats["hp"] = 100
    defender.current_hp = 40  # after hit
    _attach_ability(defender, ab, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    msgs = ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=20,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
        before_hp=60,
    )
    assert msgs
    assert get_stat_stage(defender.stat_boosts, "sp_attack") == 1


def test_stakeout_vs_just_switched_in(db, user):
    ctx = _create_battle_game(db, user, link="stakeout")
    ab = _ability(
        db,
        name="Stakeout",
        slug="stakeout",
        effects=["on_target_switched_in:self:boost_power:2"],
    )
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    _attach_ability(attacker, ab, db)
    flags = dict(target.flags or {})
    flags["just_switched_in"] = True
    target.flags = flags
    db.add(target)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(attacker, move, db, target=target) == pytest.approx(2.0)
    ca.clear_just_switched_in(target, db)
    assert ca.attacker_power_multiplier(attacker, move, db, target=target) == 1.0


def test_queenly_majesty_blocks_priority(db, user):
    ctx = _create_battle_game(db, user, link="queenly")
    ab = _ability(
        db,
        name="Queenly Majesty",
        slug="queenly_majesty",
        effects=["self_and_allies:immune_category:priority"],
    )
    defender = ctx["opponent_unit"]
    _attach_ability(defender, ab, db)
    db.commit()

    assert ca.blocks_priority_against(defender, db) is True
    assert ca.blocks_priority_against(ctx["unit"], db) is False


def test_comatose_blocks_other_status_and_can_act(db, user):
    ctx = _create_battle_game(db, user, link="comatose")
    ab = _ability(
        db,
        name="Comatose",
        slug="comatose",
        effects=["permanent_status:sleep", "can_act_while_asleep", "immune_status:all_other"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    assert ca.ensure_comatose_sleep(unit, db) is True
    assert unit.status_effects[0] == "sleep"
    assert ca.can_act_while_asleep(unit, db) is True
    assert ca.can_apply_status(unit, "burn", db) is False
    assert ca.can_apply_status(unit, "paralysis", db) is False
    assert ca.can_apply_status(unit, "sleep", db) is True


def test_triage_healing_priority_bonus(db, user):
    ctx = _create_battle_game(db, user, link="triage")
    ab = _ability(
        db,
        name="Triage",
        slug="triage",
        effects=["priority_healing:3"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    heal = models.Move(
        name="Recover",
        type="Normal",
        category="Status",
        power=None,
        effects=["self:heal_fraction:2"],
    )
    tackle = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.healing_move_priority_bonus(attacker, heal, db) == 3
    assert ca.healing_move_priority_bonus(attacker, tackle, db) == 0
    assert ca.blocks_priority_against(ctx["opponent_unit"], db) is False


def test_shadow_shield_halves_at_full_hp(db, user):
    ctx = _create_battle_game(db, user, link="shadow-shield")
    ab = _ability(
        db,
        name="Shadow Shield",
        slug="shadow_shield",
        effects=["on_hp_full:self:resist:0.5"],
    )
    defender = ctx["opponent_unit"]
    defender.current_stats = dict(defender.current_stats or {})
    defender.current_stats["hp"] = 100
    defender.current_hp = 100
    _attach_ability(defender, ab, db)
    db.commit()

    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.defender_damage_multiplier(defender, move, "normal", 1.0, db) == 0.5
    defender.current_hp = 50
    assert ca.defender_damage_multiplier(defender, move, "normal", 1.0, db) == 1.0
