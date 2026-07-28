"""Gen 8 ability wiring tests for games.py + combat_abilities."""

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
    u = models.User(username="gen8-user", email="gen8@example.com", hashed_password="x")
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


def _ability(db, *, name, slug, effects, ability_id=None, generation=8):
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


def test_transistor_and_dragons_maw_boost_type(db, user):
    ctx = _create_battle_game(db, user, link="transistor")
    ab = _ability(
        db,
        name="Transistor",
        slug="transistor",
        effects=["on_move_type:electric:self:boost_power:1.5"],
    )
    attacker = ctx["unit"]
    _attach_ability(attacker, ab, db)
    db.commit()

    electric = models.Move(name="Thunderbolt", type="Electric", category="Special", power=90)
    normal = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(attacker, electric, db) == pytest.approx(1.5)
    assert ca.attacker_power_multiplier(attacker, normal, db) == 1.0

    maw = _ability(
        db,
        name="Dragon's Maw",
        slug="dragons_maw",
        effects=["on_move_type:dragon:self:boost_power:1.5"],
    )
    _attach_ability(attacker, maw, db)
    db.commit()
    dragon = models.Move(name="Dragon Pulse", type="Dragon", category="Special", power=85)
    assert ca.attacker_power_multiplier(attacker, dragon, db) == pytest.approx(1.5)


def test_ice_scales_halves_special(db, user):
    ctx = _create_battle_game(db, user, link="ice-scales")
    ab = _ability(
        db,
        name="Ice Scales",
        slug="ice_scales",
        effects=["on_move_category:special:self:resist:0.5"],
    )
    target = ctx["opponent_unit"]
    _attach_ability(target, ab, db)
    db.commit()

    special = models.Move(name="Water Gun", type="Water", category="Special", power=40)
    physical = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.defender_damage_multiplier(target, special, "water", 1.0, db) == 0.5
    assert ca.defender_damage_multiplier(target, physical, "normal", 1.0, db) == 1.0


def test_punk_rock_boosts_and_resists_sound(db, user):
    ctx = _create_battle_game(db, user, link="punk-rock")
    ab = _ability(
        db,
        name="Punk Rock",
        slug="punk_rock",
        effects=[
            "on_move_category:sound:self:boost_power:1.3",
            "on_hit_category:sound:self:resist:0.5",
        ],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    sound = models.Move(
        name="Hyper Voice", type="Normal", category="Special", power=90, sound_based=True
    )
    quiet = models.Move(name="Tackle", type="Normal", category="Physical", power=40, sound_based=False)
    assert ca.attacker_power_multiplier(unit, sound, db) == pytest.approx(1.3)
    assert ca.attacker_power_multiplier(unit, quiet, db) == 1.0
    assert ca.defender_damage_multiplier(unit, sound, "normal", 1.0, db) == 0.5


def test_intrepid_sword_once_per_battle(db, user):
    ctx = _create_battle_game(db, user, link="intrepid-sword")
    ab = _ability(
        db,
        name="Intrepid Sword",
        slug="intrepid_sword",
        effects=["on_switch_in:self:raise_stat:attack:1:once_per_battle"],
    )
    unit = ctx["unit"]
    unit.stat_boosts = {}
    _attach_ability(unit, ab, db)
    db.commit()

    msgs = ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx.get("map_state"),
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(unit.stat_boosts, "attack") == 1

    unit.stat_boosts = {}
    db.add(unit)
    db.flush()
    ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx.get("map_state"),
        current_turn=2,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert get_stat_stage(unit.stat_boosts, "attack") == 0
    assert (unit.flags or {}).get("switch_in_raise_attack_used") is True


def test_dauntless_shield_raises_defense(db, user):
    ctx = _create_battle_game(db, user, link="dauntless-shield")
    ab = _ability(
        db,
        name="Dauntless Shield",
        slug="dauntless_shield",
        effects=["on_switch_in:self:raise_stat:defense:1:once_per_battle"],
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
        map_state=ctx.get("map_state"),
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert get_stat_stage(unit.stat_boosts, "defense") == 1


def test_gorilla_tactics_attack_mult_and_lock(db, user):
    ctx = _create_battle_game(db, user, link="gorilla-tactics")
    ab = _ability(
        db,
        name="Gorilla Tactics",
        slug="gorilla_tactics",
        effects=["self:boost_stat_mult:attack:1.5", "lock_move:first_selected"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    base = {"hp": 100, "attack": 100, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    out = ca.modify_effective_stats(unit, base, db)
    assert out["attack"] == 150

    assert ca.enforce_gorilla_tactics_lock(unit, 11, db) is None
    assert ca.enforce_gorilla_tactics_lock(unit, 22, db) == 11
    assert ca.enforce_gorilla_tactics_lock(unit, 11, db) is None


def test_propeller_tail_ignores_redirect(db, user):
    ctx = _create_battle_game(db, user, link="propeller-tail")
    tail = _ability(db, name="Propeller Tail", slug="propeller_tail", effects=["ignore_redirect"])
    rod = _ability(db, name="Lightning Rod", slug="lightning_rod", effects=["redirect:electric"])
    attacker = ctx["unit"]
    target = ctx["opponent_unit"]
    _attach_ability(attacker, tail, db)
    _attach_ability(target, rod, db)
    # Place a second foe further away that would normally not be the redirect target
    other = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=target.user_id,
        unit_id=target.unit_id,
        level=target.level,
        starting_x=5,
        starting_y=5,
        current_x=5,
        current_y=5,
        current_hp=100,
        current_stats=dict(target.current_stats or {}),
        is_fainted=False,
        can_move=True,
        flags={},
        stat_boosts={},
        status_effects=[],
        states=[],
        move_pp=[5, 5, 5, 5],
    )
    db.add(other)
    db.flush()
    db.commit()

    move = models.Move(name="Thunderbolt", type="Electric", category="Special", power=90)
    redirected = ca.redirect_targets_for_move(move, attacker, [other], [target, other], db)
    assert redirected == [other]


def test_power_spot_and_steely_spirit(db, user):
    ctx = _create_battle_game(db, user, link="power-spot")
    spot = _ability(db, name="Power Spot", slug="power_spot", effects=["adjacent_allies:boost_power:1.3"])
    steel = _ability(
        db,
        name="Steely Spirit",
        slug="steely_spirit",
        effects=["self_and_allies:on_move_type:steel:boost_power:1.5"],
    )
    attacker = ctx["unit"]
    attacker.current_x = 1
    attacker.current_y = 1
    _attach_ability(attacker, steel, db)

    ally = models.GameUnit(
        game_id=ctx["game"].id,
        user_id=user.id,
        unit_id=attacker.unit_id,
        level=attacker.level,
        starting_x=2,
        starting_y=1,
        current_x=2,
        current_y=1,
        current_hp=100,
        current_stats=dict(attacker.current_stats or {}),
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
    _attach_ability(ally, spot, db)
    db.commit()

    tackle = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    assert ca.attacker_power_multiplier(attacker, tackle, db) == pytest.approx(1.3)

    iron = models.Move(name="Iron Head", type="Steel", category="Physical", power=80)
    # Power Spot 1.3 * Steely Spirit 1.5 (self)
    assert ca.attacker_power_multiplier(attacker, iron, db) == pytest.approx(1.3 * 1.5)


def test_cotton_down_lowers_others_speed(db, user):
    ctx = _create_battle_game(db, user, link="cotton-down")
    ab = _ability(
        db,
        name="Cotton Down",
        slug="cotton_down",
        effects=["on_damage_taken:others:lower_stat:speed:1"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.stat_boosts = {}
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
    assert get_stat_stage(attacker.stat_boosts, "speed") == -1
    assert get_stat_stage(defender.stat_boosts, "speed") == 0


def test_sand_spit_sets_sandstorm(db, user):
    ctx = _create_battle_game(db, user, link="sand-spit")
    ab = _ability(
        db,
        name="Sand Spit",
        slug="sand_spit",
        effects=["on_damage_taken:weather:sandstorm"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    _attach_ability(defender, ab, db)
    db.commit()

    class FakeMap:
        weather_tiles = [[0 for _ in range(6)] for _ in range(6)]

    map_state = FakeMap()
    move = models.Move(name="Tackle", type="Normal", category="Physical", power=40)
    msgs = ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=10,
        move_type="normal",
        is_physical=True,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={
            "apply_stat_change": apply_stat_change,
            "map_state": map_state,
            "set_weather_on_map": ca.set_weather_on_map,
        },
    )
    assert msgs
    assert map_state.weather_tiles[0][0] == ca.WEATHER_TO_ID["sandstorm"]


def test_screen_cleaner_clears_screens(db, user):
    ctx = _create_battle_game(db, user, link="screen-cleaner")
    ab = _ability(
        db,
        name="Screen Cleaner",
        slug="screen_cleaner",
        effects=["on_switch_in:clear_screens"],
    )
    unit = ctx["unit"]
    opp = ctx["opponent_unit"]
    unit.states = ["reflect", 5]
    opp.states = ["light_screen", 5]
    _attach_ability(unit, ab, db)
    db.commit()

    msgs = ca.process_switch_in(
        unit,
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        map_state=ctx.get("map_state"),
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert any("screen" in m.lower() for m in msgs)
    assert not unit.states
    assert not opp.states


def test_curious_medicine_clears_ally_boosts(db, user):
    ctx = _create_battle_game(db, user, link="curious-medicine")
    ab = _ability(
        db,
        name="Curious Medicine",
        slug="curious_medicine",
        effects=["on_switch_in:allies:clear_stat_changes"],
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
        current_hp=100,
        current_stats=dict(unit.current_stats or {}),
        is_fainted=False,
        can_move=True,
        flags={},
        stat_boosts={"attack": [{"magnitude": 2, "expires_turn": 4}]},
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
        map_state=ctx.get("map_state"),
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert ally.stat_boosts == {}


def test_mirror_armor_reflects_stat_drop(db, user):
    ctx = _create_battle_game(db, user, link="mirror-armor")
    ab = _ability(db, name="Mirror Armor", slug="mirror_armor", effects=["reflect_stat_drops"])
    target = ctx["opponent_unit"]
    attacker = ctx["unit"]
    target.stat_boosts = {}
    attacker.stat_boosts = {}
    _attach_ability(target, ab, db)
    db.commit()

    apply_stat_change(target, "attack", -1, 1, db, from_opponent=True, source=attacker)
    assert get_stat_stage(target.stat_boosts, "attack") == 0
    assert get_stat_stage(attacker.stat_boosts, "attack") == -1


def test_neutralizing_gas_suppresses_other_abilities(db, user):
    ctx = _create_battle_game(db, user, link="neutralizing-gas")
    gas = _ability(db, name="Neutralizing Gas", slug="neutralizing_gas", effects=["suppress_other_abilities"])
    blaze = _ability(
        db,
        name="Blaze",
        slug="blaze",
        effects=["on_hp_below:33:on_move_type:fire:self:boost_power:1.5"],
    )
    holder = ctx["unit"]
    other = ctx["opponent_unit"]
    _attach_ability(holder, gas, db)
    _attach_ability(other, blaze, db)
    other.current_hp = 10
    other.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    db.commit()

    assert ca.field_has_neutralizing_gas(ctx["game"].id, db) is True
    assert ca.get_ability_effects(other, db) == []
    assert ca.get_ability_effects(holder, db)  # gas holder keeps ability


def test_wandering_spirit_swaps_abilities(db, user):
    ctx = _create_battle_game(db, user, link="wandering-spirit")
    spirit = _ability(
        db, name="Wandering Spirit", slug="wandering_spirit", effects=["on_contact:swap_abilities"]
    )
    intimidate = _ability(
        db,
        name="Intimidate",
        slug="intimidate",
        effects=["on_switch_in:opponents:lower_stat:attack:1"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    _attach_ability(defender, spirit, db)
    _attach_ability(attacker, intimidate, db)
    db.commit()

    msgs = ca.process_contact_abilities(
        attacker,
        defender,
        makes_contact=True,
        damage=20,
        db=db,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert (attacker.flags or {}).get("ability_id") == spirit.id
    assert (defender.flags or {}).get("ability_id") == intimidate.id


def test_perish_body_applies_perish(db, user):
    ctx = _create_battle_game(db, user, link="perish-body")
    ab = _ability(
        db,
        name="Perish Body",
        slug="perish_body",
        effects=["on_contact:both:apply_state:perish:3"],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    attacker.states = []
    defender.states = []
    _attach_ability(defender, ab, db)
    db.commit()

    msgs = ca.process_contact_abilities(
        attacker,
        defender,
        makes_contact=True,
        damage=15,
        db=db,
        helpers={},
    )
    assert msgs
    assert attacker.states[0] == "perish"
    assert defender.states[0] == "perish"
    assert attacker.states[1] == 3


def test_pastel_veil_blocks_ally_poison(db, user):
    ctx = _create_battle_game(db, user, link="pastel-veil")
    ab = _ability(
        db,
        name="Pastel Veil",
        slug="pastel_veil",
        effects=[
            "self_and_allies:immune_status:poison",
            "self_and_allies:immune_status:badly_poison",
        ],
    )
    holder = ctx["unit"]
    _attach_ability(holder, ab, db)
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

    assert ca.can_apply_status(ally, "poison", db) is False
    assert ca.can_apply_status(ally, "burn", db) is True


def test_chilling_neigh_raises_attack_on_ko(db, user):
    ctx = _create_battle_game(db, user, link="chilling-neigh")
    ab = _ability(
        db,
        name="Chilling Neigh",
        slug="chilling_neigh",
        effects=["on_ko:self:raise_stat:attack:1"],
    )
    attacker = ctx["unit"]
    fainted = ctx["opponent_unit"]
    attacker.stat_boosts = {}
    _attach_ability(attacker, ab, db)
    db.commit()

    msgs = ca.process_on_ko(
        attacker,
        fainted,
        db,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert msgs
    assert get_stat_stage(attacker.stat_boosts, "attack") == 1


def test_mimicry_changes_type_on_terrain(db, user):
    ctx = _create_battle_game(db, user, link="mimicry")
    ab = _ability(db, name="Mimicry", slug="mimicry", effects=["on_terrain:change_type:terrain"])
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    assert ca.update_mimicry_types(unit, TERRAIN_TO_ID["electric"], db) is True
    assert "electric" in ca.get_battle_types(unit, db)
    assert ca.update_mimicry_types(unit, 0, db) is True
    assert "battle_types" not in (unit.flags or {})


def test_ice_face_blocks_physical_and_restores_in_hail(db, user):
    ctx = _create_battle_game(db, user, link="ice-face")
    ab = _ability(
        db,
        name="Ice Face",
        slug="ice_face",
        effects=[
            "on_physical_hit:block_and_change_forme:noice",
            "on_weather:hail:restore_forme:ice",
        ],
    )
    unit = ctx["opponent_unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    dmg, msgs = ca.apply_ice_face(unit, 40, is_physical=True, db=db)
    assert dmg == 0
    assert msgs
    assert (unit.flags or {}).get("forme") == "noice"

    dmg2, _ = ca.apply_ice_face(unit, 40, is_physical=True, db=db)
    assert dmg2 == 40

    assert ca.restore_ice_face_on_hail(unit, ca.WEATHER_TO_ID["hail"], db) is True
    assert (unit.flags or {}).get("forme") == "ice"


def test_hunger_switch_toggles_forme(db, user):
    ctx = _create_battle_game(db, user, link="hunger-switch")
    ab = _ability(
        db,
        name="Hunger Switch",
        slug="hunger_switch",
        effects=["on_turn_end:toggle_forme:full_belly_hangry"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        weather_tiles=None,
        current_turn=1,
        helpers={},
    )
    assert (unit.flags or {}).get("forme") == "hangry"

    ca.process_end_of_turn_abilities(
        [unit],
        db,
        game=ctx["game"],
        game_state=ctx["state"],
        weather_tiles=None,
        current_turn=2,
        helpers={},
    )
    assert (unit.flags or {}).get("forme") == "full_belly"


def test_libero_changes_type_like_protean(db, user):
    ctx = _create_battle_game(db, user, link="libero")
    ab = _ability(
        db,
        name="Libero",
        slug="libero",
        effects=["on_move_use:self:change_type:move_type:once_per_switch_in"],
    )
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()

    assert ca.process_protean(unit, "fire", db) is True
    assert "fire" in ca.get_battle_types(unit, db)
    assert ca.process_protean(unit, "water", db) is False


def test_steam_engine_maxes_speed_on_fire_or_water(db, user):
    ctx = _create_battle_game(db, user, link="steam-engine")
    ab = _ability(
        db,
        name="Steam Engine",
        slug="steam_engine",
        effects=[
            "on_hit_type:fire:self:raise_stat:speed:6",
            "on_hit_type:water:self:raise_stat:speed:6",
        ],
    )
    defender = ctx["opponent_unit"]
    attacker = ctx["unit"]
    defender.stat_boosts = {}
    _attach_ability(defender, ab, db)
    db.commit()

    move = models.Move(name="Ember", type="Fire", category="Special", power=40)
    ca.process_defender_hit_reactions(
        attacker,
        defender,
        move,
        damage=10,
        move_type="fire",
        is_physical=False,
        was_crit=False,
        db=db,
        current_turn=1,
        helpers={"apply_stat_change": apply_stat_change},
    )
    assert get_stat_stage(defender.stat_boosts, "speed") == 6


def test_ripen_doubles_berry_effects(db, user):
    ctx = _create_battle_game(db, user, link="ripen")
    ab = _ability(db, name="Ripen", slug="ripen", effects=["double_berry_effects"])
    unit = ctx["unit"]
    _attach_ability(unit, ab, db)
    db.commit()
    assert ca.berry_effect_multiplier(unit, db) == 2.0


def test_unseen_fist_and_quick_draw_helpers(db, user):
    ctx = _create_battle_game(db, user, link="unseen-fist")
    fist = _ability(
        db, name="Unseen Fist", slug="unseen_fist", effects=["contact_bypass_protect:0.25"]
    )
    draw = _ability(
        db, name="Quick Draw", slug="quick_draw", effects=["on_same_priority:go_first:100"]
    )
    unit = ctx["unit"]
    _attach_ability(unit, fist, db)
    db.commit()
    assert ca.contact_bypasses_protect(unit, db) is True

    _attach_ability(unit, draw, db)
    db.commit()
    assert ca.quick_draw_goes_first(unit, db) is True


def test_gulp_missile_catch_and_spit(db, user):
    ctx = _create_battle_game(db, user, link="gulp-missile")
    ab = _ability(
        db,
        name="Gulp Missile",
        slug="gulp_missile",
        effects=["on_surf_or_dive:catch_prey", "on_damage_taken:spit_prey"],
    )
    unit = ctx["unit"]
    foe = ctx["opponent_unit"]
    _attach_ability(unit, ab, db)
    foe.current_hp = 100
    foe.current_stats = {"hp": 100, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50}
    db.commit()

    surf = models.Move(name="Surf", type="Water", category="Special", power=90)
    assert ca.maybe_catch_gulp_prey(unit, surf, db) is True
    assert (unit.flags or {}).get("gulp_prey")

    msgs = ca.process_gulp_missile_spit(unit, foe, damage=20, db=db)
    assert msgs
    assert foe.current_hp == 75
    assert "gulp_prey" not in (unit.flags or {})
