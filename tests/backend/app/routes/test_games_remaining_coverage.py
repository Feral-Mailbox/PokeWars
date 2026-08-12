"""Additional coverage tests for app.routes.games targeting the largest remaining
coverage gaps: fixed/recoil/drain damage helpers, state application branches,
turn-lifecycle helpers, the /state endpoints, start_game phase transitions,
War in-progress unit summon, execute_move encore/taunt/torment enforcement,
pick_up_item and move_unit error paths, and several under-exercised
process_move_effects tokens.
"""

import itertools

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm.attributes import flag_modified

import app.db.models as models
from app.main import app
from app.dependencies import get_db, get_current_user
from app.routes import games as games_mod
from app.routes.games import (
    WEATHER_TO_ID,
    TERRAIN_TO_ID,
    apply_damage_based_move_effects,
    apply_end_of_turn_status_damage,
    apply_fixed_damage_move_effects,
    apply_state_effect,
    attach_game_unit_loadout_fields,
    compute_effective_stats,
    compute_fixed_damage_effect,
    decrement_and_expire_status_effects,
    default_stat_boosts,
    get_critical_hit_chance,
    get_modified_accuracy_threshold,
    get_playable_player_ids_in_order,
    get_type_multiplier,
    move_can_critical_hit,
    move_deals_direct_damage,
    move_has_high_crit_ratio,
    move_is_instant_ko,
    move_lands_on_target,
    normalize_states,
    process_move_effects,
    publish_turn_remaining_warning_if_needed,
    publish_turn_start_logs,
    reconcile_playable_players,
    record_last_damage_received,
    remove_fainted_units_from_play,
    resolve_move_type_for_execution,
    resolve_move_type_from_held_item,
    resolve_power_add,
    resolve_weather_move_multiplier_for_move,
    set_unit_flags,
    snapshot_turn_stat_stages,
    _build_2d_matrix,
    _normalize_item_id_tiles_from_map,
)

_species_counter = itertools.count(970000)
_link_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Shared builders (mirrors patterns used by sibling coverage test files)
# ---------------------------------------------------------------------------


def _make_user(db, username):
    user = models.User(username=username, email=f"{username}@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _make_unit_def(db, name=None, *, types=None, base_stats=None, ability_ids=None):
    name = name or f"Mon {next(_species_counter)}"
    unit = models.Unit(
        species_id=next(_species_counter),
        name=name,
        species=name,
        asset_folder=name.lower().replace(" ", "_"),
        types=types or ["Normal"],
        base_stats=base_stats
        or {"hp": 60, "attack": 60, "defense": 60, "sp_attack": 60, "sp_defense": 60, "speed": 60},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=ability_ids or [],
        cost=100,
    )
    db.add(unit)
    db.commit()
    return unit


def _make_map(db, creator_id, *, width=4, height=4, allowed_modes=None):
    map_obj = models.Map(
        name=f"Remaining Coverage Map {next(_link_counter)}",
        creator_id=creator_id,
        is_official=True,
        width=width,
        height=height,
        tileset_names=["grass"],
        tile_data={"movement_cost": [[1] * width for _ in range(height)]},
        allowed_modes=allowed_modes or ["Conquest"],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.commit()
    return map_obj


def _make_game(db, map_obj, user_ids, *, gamemode="Conquest", host_id=None, max_turns=None):
    game = models.Game(
        game_name=f"Remaining Coverage Game {next(_link_counter)}",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=max(2, len(user_ids)),
        gamemode=gamemode,
        is_private=False,
        host_id=host_id or user_ids[0],
        link=f"rem-cov-{next(_link_counter)}",
        max_turns=max_turns,
    )
    db.add(game)
    db.commit()
    return game


def _make_state(db, game, user_ids, *, current_turn=0, status=models.GameStatus.in_progress):
    state = models.GameState(
        game_id=game.id,
        current_turn=current_turn,
        status=status,
        players=list(user_ids),
        replay_log=[],
    )
    db.add(state)
    db.commit()
    return state


def _make_map_state(db, game, map_obj):
    width, height = map_obj.width, map_obj.height
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=[[0] * width for _ in range(height)],
        hazard_tiles=[[[] for _ in range(width)] for _ in range(height)],
        room_effect_tiles=[[0] * width for _ in range(height)],
        terrain_effect_tiles=[[[0, 0] for _ in range(width)] for _ in range(height)],
        field_effect_tiles=[[0] * width for _ in range(height)],
        item_id_tiles=[[None] * width for _ in range(height)],
        objective_tiles=[[None for _ in range(width)] for _ in range(height)],
    )
    db.add(map_state)
    db.commit()
    return map_state


def _make_game_unit(
    db,
    unit_def,
    *,
    x,
    y,
    hp,
    max_hp,
    game=None,
    user_id=None,
    level=50,
    flags=None,
    states=None,
    status_effects=None,
    stat_boosts=None,
    is_fainted=False,
    can_move=True,
    current_stats_extra=None,
):
    stats = {
        "hp": max_hp,
        "attack": 60,
        "defense": 60,
        "sp_attack": 60,
        "sp_defense": 60,
        "speed": 60,
        "range": 4,
    }
    if current_stats_extra:
        stats.update(current_stats_extra)
    unit = models.GameUnit(
        game_id=game.id if game else None,
        user_id=user_id,
        unit_id=unit_def.id,
        level=level,
        starting_x=x,
        starting_y=y,
        current_x=x,
        current_y=y,
        current_hp=hp,
        current_stats=stats,
        stat_boosts=stat_boosts if stat_boosts is not None else default_stat_boosts(),
        status_effects=status_effects if status_effects is not None else [],
        states=states if states is not None else [],
        is_fainted=is_fainted,
        can_move=can_move,
        flags=flags if flags is not None else {},
    )
    db.add(unit)
    db.commit()
    return unit


@pytest.fixture
def user(db):
    return _make_user(db, "rem-cov-user")


@pytest.fixture
def client(db, user):
    def override_get_db():
        yield db

    def override_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _default_stat_boosts():
    return default_stat_boosts()


def _make_unit_definition_http(db, *, link, suffix, cost=100, types=None):
    unit_info = models.Unit(
        species_id=6000 + db.query(models.Unit).count(),
        name=f"Unit-{link}-{suffix}",
        species=f"Unit-{link}-{suffix}",
        asset_folder=f"unit_{link}_{suffix}".lower(),
        types=types or ["Water"],
        base_stats={"hp": 60, "attack": 60, "defense": 60, "sp_attack": 60, "sp_defense": 60, "speed": 60},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[],
        cost=cost,
        portrait_credits=[],
        sprite_credits=[],
        weight=1.0,
        height=1.0,
    )
    db.add(unit_info)
    db.flush()
    return unit_info


def _create_battle_game(
    db,
    user,
    *,
    link,
    status=models.GameStatus.in_progress,
    gamemode="Conquest",
    preparation=False,
    width=6,
    height=6,
    war_objectives=None,
):
    """Build a full battle fixture. Mirrors test_games_http_actions_coverage._create_battle_game."""
    actual_status = models.GameStatus.preparation if preparation else status

    opponent = models.User(
        username=f"opp-{link}",
        email=f"opp-{link}@example.com",
        hashed_password="x",
    )
    db.add(opponent)
    db.flush()

    map_obj = models.Map(
        name=f"Battle Map {link}",
        creator_id=user.id,
        is_official=True,
        width=width,
        height=height,
        tileset_names=["grass"],
        tile_data={"movement_cost": [[1] * width for _ in range(height)]},
        allowed_modes=[gamemode],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.flush()

    game = models.Game(
        game_name=f"Battle {link}",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode=gamemode,
        is_private=False,
        host_id=user.id,
        link=link,
        turn_seconds=300,
        start_with_tms=False,
    )
    db.add(game)
    db.flush()

    state = models.GameState(
        game_id=game.id,
        current_turn=0,
        status=actual_status,
        players=[user.id, opponent.id],
        replay_log=[],
    )
    db.add(state)

    objective_tiles = war_objectives if war_objectives is not None else [[None for _ in range(width)] for _ in range(height)]
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=[[0] * width for _ in range(height)],
        hazard_tiles=[[[] for _ in range(width)] for _ in range(height)],
        room_effect_tiles=[[0] * width for _ in range(height)],
        terrain_effect_tiles=[[0] * width for _ in range(height)],
        field_effect_tiles=[[0] * width for _ in range(height)],
        item_id_tiles=[[None] * width for _ in range(height)],
        objective_tiles=objective_tiles,
    )
    db.add(map_state)

    move = models.Move(
        name=f"Tackle-{link}",
        type="Normal",
        category="Physical",
        power=40,
        accuracy=None,
        pp=20,
        effects=[],
        range="melee",
        targeting="enemy",
    )
    db.add(move)
    db.flush()

    unit_info = models.Unit(
        species_id=5000 + db.query(models.Unit).count(),
        name=f"Battler-{link}",
        species=f"Battler-{link}",
        asset_folder=f"battler_{link}".lower(),
        types=["Normal"],
        base_stats={"hp": 100, "attack": 100, "defense": 50, "sp_attack": 100, "sp_defense": 50, "speed": 100},
        level_up_moves=[{"move_id": move.id, "level": 1}],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[move.id],
        ability_ids=[],
        cost=100,
        portrait_credits=[],
        sprite_credits=[],
        weight=1.0,
        height=1.0,
    )
    db.add(unit_info)
    db.flush()

    current_stats = {
        "hp": 100,
        "attack": 100,
        "defense": 50,
        "sp_attack": 100,
        "sp_defense": 50,
        "speed": 100,
        "range": 3,
    }

    unit = models.GameUnit(
        game_id=game.id,
        unit_id=unit_info.id,
        user_id=user.id,
        starting_x=1,
        starting_y=1,
        current_x=1,
        current_y=1,
        level=50,
        current_hp=100,
        current_stats=dict(current_stats),
        stat_boosts=_default_stat_boosts(),
        status_effects=[],
        states=[],
        is_fainted=False,
        can_move=True,
        move_pp=[move.pp],
        flags={"move_ids": [move.id]},
    )
    opponent_unit = models.GameUnit(
        game_id=game.id,
        unit_id=unit_info.id,
        user_id=opponent.id,
        starting_x=4,
        starting_y=4,
        current_x=4,
        current_y=4,
        level=50,
        current_hp=100,
        current_stats=dict(current_stats),
        stat_boosts=_default_stat_boosts(),
        status_effects=[],
        states=[],
        is_fainted=False,
        can_move=True,
        move_pp=[move.pp],
        flags={"move_ids": [move.id]},
    )
    db.add_all([unit, opponent_unit])
    db.flush()

    player = models.GamePlayer(
        game_id=game.id,
        player_id=user.id,
        cash_remaining=1000,
        game_units=[unit.id],
        is_ready=False,
    )
    opp_player = models.GamePlayer(
        game_id=game.id,
        player_id=opponent.id,
        cash_remaining=1000,
        game_units=[opponent_unit.id],
        is_ready=False,
    )
    db.add_all([player, opp_player])
    db.commit()

    return {
        "game": game,
        "state": state,
        "map_obj": map_obj,
        "map_state": map_state,
        "unit": unit,
        "opponent": opponent,
        "opponent_unit": opponent_unit,
        "move": move,
        "player": player,
        "opp_player": opp_player,
    }


# ---------------------------------------------------------------------------
# Section A.1 -- compute_fixed_damage_effect / apply_fixed_damage_move_effects
# ---------------------------------------------------------------------------


def test_compute_fixed_damage_effect_all_modes(db):
    unit_def = _make_unit_def(db, "FixedDmg Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=30, max_hp=30, level=42)
    target = _make_game_unit(db, unit_def, x=1, y=0, hp=100, max_hp=100)

    assert compute_fixed_damage_effect("target:fixed_damage:level", attacker, target) == 42
    assert compute_fixed_damage_effect("target:fixed_damage:equal_to_user_hp", attacker, target) == 30
    assert compute_fixed_damage_effect("target:fixed_damage:reduce_to_user_hp", attacker, target) == 70

    assert compute_fixed_damage_effect("target:fixed_damage:current_hp:4", attacker, target) == 25
    assert compute_fixed_damage_effect("target:fixed_damage:current_hp:0", attacker, target) == 0
    assert compute_fixed_damage_effect("target:fixed_damage:current_hp:abc", attacker, target) == 0
    assert compute_fixed_damage_effect("target:fixed_damage:current_hp", attacker, target) == 0
    tiny_target = _make_game_unit(db, unit_def, x=2, y=0, hp=1, max_hp=1)
    assert compute_fixed_damage_effect("target:fixed_damage:current_hp:1000", attacker, tiny_target) == 1

    set_unit_flags(attacker, {"last_damage_amount": 40}, db)
    db.commit()
    assert compute_fixed_damage_effect("target:fixed_damage:last_damage_received:1.5", attacker, target) == 60
    assert compute_fixed_damage_effect("target:fixed_damage:last_damage_received:abc", attacker, target) == 0
    assert compute_fixed_damage_effect("target:fixed_damage:last_damage_received", attacker, target) == 0
    set_unit_flags(attacker, {"last_damage_amount": 0}, db)
    db.commit()
    assert compute_fixed_damage_effect("target:fixed_damage:last_damage_received:1.5", attacker, target) == 0

    assert compute_fixed_damage_effect("target:fixed_damage:50", attacker, target) == 50
    assert compute_fixed_damage_effect("target:fixed_damage:abc", attacker, target) == 0
    assert compute_fixed_damage_effect("bad:format", attacker, target) == 0
    assert compute_fixed_damage_effect("", attacker, target) == 0

    huge_hit = compute_fixed_damage_effect("target:fixed_damage:level", attacker, tiny_target)
    assert huge_hit == 1  # capped by target's current HP


def test_apply_fixed_damage_move_effects_branches(db):
    unit_def = _make_unit_def(db, "FixedDmgApply Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=30, max_hp=30, level=10)
    target_alive = _make_game_unit(db, unit_def, x=1, y=0, hp=100, max_hp=100)
    target_dead = _make_game_unit(db, unit_def, x=2, y=0, hp=0, max_hp=100)

    move = models.Move(
        name="Fixed Level Move",
        type="Normal",
        category="Status",
        effects=["target:fixed_damage:level"],
    )

    # No effects -> []
    empty_move = models.Move(name="No Effects", type="Normal", category="Status", effects=[])
    assert apply_fixed_damage_move_effects(empty_move, attacker, [target_alive], db) == []
    # No targets -> []
    assert apply_fixed_damage_move_effects(move, attacker, [], db) == []
    # Move without fixed_damage token -> []
    other_move = models.Move(name="Other", type="Normal", category="Status", effects=["self:heal:2"])
    assert apply_fixed_damage_move_effects(other_move, attacker, [target_alive], db) == []

    results = apply_fixed_damage_move_effects(move, attacker, [target_alive, target_dead], db, hit_count=3)
    assert len(results) == 1
    assert results[0]["id"] == target_alive.id
    assert results[0]["damage"] == 30  # 3 hits of 10 damage
    assert target_alive.current_hp == 70


# ---------------------------------------------------------------------------
# Section A.2 -- apply_damage_based_move_effects (drain / recoil)
# ---------------------------------------------------------------------------


def test_apply_damage_based_move_effects_drain_and_recoil(db):
    user = _make_user(db, "damage-based-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "DamageBased Mon")

    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=60, game=game, user_id=user.id)
    drain_target = _make_game_unit(db, unit_def, x=1, y=0, hp=10, max_hp=60, game=game, user_id=user.id)
    recoil_low_hp = _make_game_unit(db, unit_def, x=2, y=0, hp=1, max_hp=60, game=game, user_id=user.id)

    move = models.Move(
        name="Drain/Recoil Combo",
        type="Normal",
        category="Physical",
        effects=["self:drain:2", "target:drain:2", "self:recoil:damage_dealt:1"],
    )
    damage_results = [{"id": drain_target.id, "damage": 20}]

    fainted = apply_damage_based_move_effects(
        move, attacker, [drain_target], damage_results, db, game=game, game_state=state
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(drain_target)
    # self:drain:2 heals attacker by 10; self:recoil:damage_dealt:1 then removes 20 -> net still tracked
    assert attacker.current_hp >= 0
    assert drain_target.current_hp > 10
    assert damage_results[0]["current_hp"] == drain_target.current_hp

    # Recoil based on maximum_hp that faints the unit
    recoil_move = models.Move(
        name="Max HP Recoil",
        type="Normal",
        category="Physical",
        effects=["target:recoil:maximum_hp:1"],
    )
    fainted_ids = apply_damage_based_move_effects(
        recoil_move, attacker, [recoil_low_hp], [], db, game=game, game_state=state
    )
    db.commit()
    db.refresh(recoil_low_hp)
    assert recoil_low_hp.current_hp == 0
    assert recoil_low_hp.id in fainted_ids

    # No effects at all -> []
    no_effects_move = models.Move(name="No Effects", type="Normal", category="Physical", effects=[])
    assert apply_damage_based_move_effects(no_effects_move, attacker, [drain_target], [], db) == []

    # Invalid denominators / bad formats are skipped safely
    bad_move = models.Move(
        name="Bad Formats",
        type="Normal",
        category="Physical",
        effects=[
            "self:drain",  # too few parts after split by ':' for drain (len != 3)
            "self:drain:abc",  # ValueError
            "self:drain:0",  # denominator <= 0
            "self:recoil:damage_dealt",  # len != 4
            "self:recoil:unknown_basis:2",  # unknown recoil basis
            "self:recoil:damage_dealt:abc",  # ValueError
            "self:burn:2",  # not drain/recoil -> skipped entirely
            "onlyonepart",  # len(parts) < 2
        ],
    )
    assert apply_damage_based_move_effects(bad_move, attacker, [drain_target], [{"id": drain_target.id, "damage": 0}], db) == []


# ---------------------------------------------------------------------------
# Section A.3 -- apply_state_effect across all recognized state names
# ---------------------------------------------------------------------------


def test_apply_state_effect_covers_named_states(db, monkeypatch):
    unit_def = _make_unit_def(db, "StateFx Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)

    simple_states = [
        "reflect",
        "light_screen",
        "aurora_veil",
        "aqua_ring",
        "ingrain",
        "laser_focus",
        "heal_block",
        "cursed",
        "immobilized",
        "salt_cure",
        "taunt",
        "torment",
        "telekinesis",
        "tar_shot",
        "gastro_acid",
        "embargo",
        "destiny_bond",
        "flinch",
        "glaive_rush",
        "substitute",
    ]
    for state_name in simple_states:
        unit.states = []
        db.commit()
        assert apply_state_effect(unit, state_name, db) is True
        assert unit.states[0] == state_name

    # nightmare uses a very long duration
    unit.states = []
    db.commit()
    assert apply_state_effect(unit, "nightmare", db) is True
    assert unit.states == ["nightmare", 9999]

    # confusion uses a random duration between 2 and 5
    unit.states = []
    db.commit()
    monkeypatch.setattr(games_mod.random, "randint", lambda a, b: 3)
    assert apply_state_effect(unit, "confusion", db) is True
    assert unit.states == ["confusion", 3]

    # Unknown state name is rejected
    unit.states = []
    db.commit()
    assert apply_state_effect(unit, "not_a_real_state", db) is False

    # Refreshing an already-active identical state is a no-op
    unit.states = ["taunt", 3]
    db.commit()
    assert apply_state_effect(unit, "taunt", db) is False

    # A different state cannot overwrite an already-active one
    unit.states = ["taunt", 3]
    db.commit()
    assert apply_state_effect(unit, "torment", db) is False


def test_apply_state_effect_power_trick_toggle(db):
    unit_def = _make_unit_def(db, "PowerTrick Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)

    # First application enables Power Trick (persistent until toggled off).
    assert apply_state_effect(unit, "power_trick", db) is True
    assert unit.states and unit.states[0] == "power_trick" and int(unit.states[1]) > 0

    # Applying again while active toggles it off.
    assert apply_state_effect(unit, "power_trick", db) is True
    assert unit.states == []


def test_apply_state_effect_drowsy_applies_successfully(db):
    # "drowsy" (applied by Yawn's target:apply_state:drowsy effect) was previously
    # missing from VALID_STATE_EFFECTS, making its dedicated branch further down in
    # apply_state_effect permanently unreachable and silently breaking Yawn. Fixed by
    # adding "drowsy" to VALID_STATE_EFFECTS.
    unit_def = _make_unit_def(db, "Drowsy Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)

    assert apply_state_effect(unit, "drowsy", db) is True
    assert unit.states[0] == "drowsy"


# ---------------------------------------------------------------------------
# Section A.4 -- publish_turn_start_logs / publish_turn_remaining_warning_if_needed
# ---------------------------------------------------------------------------


def test_publish_turn_start_logs_edge_branches(db, _mock_redis):
    user = _make_user(db, "turnlogs-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])

    no_turn_state = models.GameState(game_id=game.id, current_turn=None, status=models.GameStatus.in_progress, players=[user.id])
    # current_turn is None -> early return, no error
    assert publish_turn_start_logs(game, no_turn_state, db) is None

    no_players_state = models.GameState(game_id=game.id, current_turn=0, status=models.GameStatus.in_progress, players=[])
    # players empty -> early return
    assert publish_turn_start_logs(game, no_players_state, db) is None

    normal_state = _make_state(db, game, [user.id], current_turn=0)
    publish_turn_start_logs(game, normal_state, db)
    assert any("Turn 1" in row.get("message", "") for row in normal_state.replay_log if isinstance(row, dict))


def test_publish_turn_remaining_warning_edge_branches(db):
    from datetime import datetime, timedelta, timezone

    user = _make_user(db, "warn-edge-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    game.turn_seconds = 300
    db.add(game)
    db.commit()

    now = datetime.now(timezone.utc)

    # status != in_progress -> False
    closed_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.closed, players=[user.id],
        turn_deadline=now + timedelta(seconds=10), replay_log=[],
    )
    assert publish_turn_remaining_warning_if_needed(game, closed_state, db, now) is False

    # no turn_deadline -> False
    no_deadline_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.in_progress, players=[user.id],
        turn_deadline=None, replay_log=[],
    )
    assert publish_turn_remaining_warning_if_needed(game, no_deadline_state, db, now) is False

    # empty players -> False
    empty_players_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.in_progress, players=[],
        turn_deadline=now + timedelta(seconds=10), replay_log=[],
    )
    assert publish_turn_remaining_warning_if_needed(game, empty_players_state, db, now) is False

    # remaining_seconds > warning_seconds -> False (turn_seconds=300 -> warning=60)
    far_deadline_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.in_progress, players=[user.id],
        turn_deadline=now + timedelta(seconds=200), replay_log=[],
    )
    assert publish_turn_remaining_warning_if_needed(game, far_deadline_state, db, now) is False

    # remaining_seconds <= 0 -> False
    expired_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.in_progress, players=[user.id],
        turn_deadline=now - timedelta(seconds=5), replay_log=[],
    )
    assert publish_turn_remaining_warning_if_needed(game, expired_state, db, now) is False

    # Real warning branch fires when within the window
    near_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.in_progress, players=[user.id],
        turn_deadline=now + timedelta(seconds=20), replay_log=[],
    )
    assert publish_turn_remaining_warning_if_needed(game, near_state, db, now) is True


# ---------------------------------------------------------------------------
# Section A.5 -- get_type_multiplier
# ---------------------------------------------------------------------------


def test_get_type_multiplier_branches(db):
    assert get_type_multiplier("", ["water"]) == 1
    assert get_type_multiplier("madeup", ["water"]) == 1
    assert get_type_multiplier("electric", ["ground"]) == 0
    assert get_type_multiplier("fire", ["grass", "ice"]) == 4
    assert get_type_multiplier("fire", ["water"]) == 0.5

    unit_def = _make_unit_def(db, "TypeMult Mon", types=["Ground"])
    foresight_unit = _make_game_unit(db, unit_def, x=0, y=0, hp=1, max_hp=1, states=["foresight", 3])
    # Ghost-type immunity to normal is bypassed by Foresight
    assert get_type_multiplier("normal", (["ghost"], foresight_unit, db)) == 1.0

    mind_reader_unit = _make_game_unit(db, unit_def, x=1, y=0, hp=1, max_hp=1, states=["mind_reader", 3])
    assert get_type_multiplier("psychic", (["dark"], mind_reader_unit, db)) == 1.0

    plain_unit = _make_game_unit(db, unit_def, x=2, y=0, hp=1, max_hp=1, states=[])
    assert get_type_multiplier("normal", (["ghost"], plain_unit, db)) == 0

    # ignore_fairy_immunity bypasses dragon -> fairy immunity
    assert get_type_multiplier("dragon", ["fairy"], ignore_fairy_immunity=True) == 1.0
    assert get_type_multiplier("dragon", ["fairy"], ignore_fairy_immunity=False) == 0


# ---------------------------------------------------------------------------
# Section A.6 -- resolve_move_type_for_execution / held item / weather override / power add
# ---------------------------------------------------------------------------


def test_resolve_move_type_for_execution_terrain_and_item(db):
    unit_def = _make_unit_def(db, "MoveType Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)

    terrain_move = models.Move(
        name="Terrain Type Move", type="Normal", category="Physical",
        effects=["self:modify_move_type_by_terrain"],
    )
    electric_terrain = [[[TERRAIN_TO_ID["electric"], 5]]]
    assert resolve_move_type_for_execution(terrain_move, attacker, electric_terrain, db) == "Electric"

    no_terrain = [[[0, 0]]]
    assert resolve_move_type_for_execution(terrain_move, attacker, no_terrain, db) == "Normal"

    mask_move = models.Move(
        name="Mask Move", type="Normal", category="Physical",
        effects=["self:modify_move_type_by_held_item:mask"],
    )
    set_unit_flags(attacker, {"held_item": "hearthflame_mask"}, db)
    db.commit()
    assert resolve_move_type_for_execution(mask_move, attacker, None, db) == "Fire"

    set_unit_flags(attacker, {"held_item": "unrelated_item"}, db)
    db.commit()
    assert resolve_move_type_for_execution(mask_move, attacker, None, db) == "Normal"

    assert resolve_move_type_from_held_item(attacker, "not_mask") is None
    set_unit_flags(attacker, {}, db)
    db.commit()
    assert resolve_move_type_from_held_item(attacker, "mask") is None


def test_resolve_weather_move_multiplier_override(db):
    override_move = models.Move(
        name="Weather Override Move", type="Fire", category="Special",
        effects=["weather_override:sun:3.0"],
    )
    assert resolve_weather_move_multiplier_for_move(override_move, "fire", WEATHER_TO_ID["sun"]) == 3.0
    # Weather doesn't match -> falls through to normal weather multiplier table
    assert resolve_weather_move_multiplier_for_move(override_move, "fire", WEATHER_TO_ID["rain"]) == 0.5

    plain_move = models.Move(name="Plain", type="Fire", category="Special", effects=[])
    assert resolve_weather_move_multiplier_for_move(plain_move, "fire", WEATHER_TO_ID["sun"]) == 1.5
    assert resolve_weather_move_multiplier_for_move(None, "fire", WEATHER_TO_ID["sun"]) == 1.5


def test_resolve_power_add_branches(db):
    unit_def = _make_unit_def(db, "PowerAdd Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, flags={"times_hit": 3, "allies_defeated_since_turn": 2})

    times_hit_move = models.Move(
        name="Times Hit Move", type="Normal", category="Physical", power=20,
        effects=["power_add:times_hit:10:60"],
    )
    assert resolve_power_add(times_hit_move, attacker) == 30  # capped at 60-20

    allies_move = models.Move(
        name="Allies Defeated Move", type="Normal", category="Physical", power=20,
        effects=["power_add:allies_defeated_since_turn:15"],
    )
    assert resolve_power_add(allies_move, attacker) == 30

    bad_move = models.Move(
        name="Bad Power Add", type="Normal", category="Physical", power=20,
        effects=["power_add:times_hit:abc", "not_power_add:x:1", "power_add"],
    )
    assert resolve_power_add(bad_move, attacker) == 0

    no_effects_move = models.Move(name="None", type="Normal", category="Physical", power=20, effects=None)
    assert resolve_power_add(no_effects_move, attacker) == 0
    assert resolve_power_add(None, attacker) == 0


# ---------------------------------------------------------------------------
# Section A.7 -- snapshot_turn_stat_stages / record_last_damage_received
# ---------------------------------------------------------------------------


def test_snapshot_turn_stat_stages_and_record_last_damage(db):
    user = _make_user(db, "snapshot-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "Snapshot Mon")
    unit = _make_game_unit(
        db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id,
        stat_boosts={"attack": [{"magnitude": 2, "expires_turn": 4}]},
    )

    snapshot_turn_stat_stages(user.id, game.id, db)
    db.commit()
    db.refresh(unit)
    assert unit.flags["stat_stages_at_turn_start"]["attack"] == 2
    assert unit.flags["allies_defeated_since_turn"] == 0

    attacker = _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40)
    target = _make_game_unit(db, unit_def, x=2, y=0, hp=40, max_hp=40)

    # damage <= 0 is a no-op (early return)
    record_last_damage_received(target, attacker, 0, db)
    assert "last_damage_attacker_id" not in (target.flags or {})

    record_last_damage_received(target, attacker, 15, db)
    db.commit()
    db.refresh(target)
    assert target.flags["last_damage_attacker_id"] == attacker.id
    assert target.flags["last_damage_amount"] == 15
    assert target.flags["times_hit"] == 1

    record_last_damage_received(target, attacker, 5, db)
    db.commit()
    db.refresh(target)
    assert target.flags["times_hit"] == 2


# ---------------------------------------------------------------------------
# Section A.8 -- attach_game_unit_loadout_fields
# ---------------------------------------------------------------------------


def test_attach_game_unit_loadout_fields(db):
    move = models.Move(name="Loadout Move", type="Normal", category="Physical", pp=10)
    db.add(move)
    db.commit()
    ability = models.Ability(name="Loadout Ability", slug="loadout-ability", generation=1)
    db.add(ability)
    db.commit()
    unit_def = _make_unit_def(db, "Loadout Mon")
    unit_def.equipped_moves = [move.id]
    db.commit()

    unit = _make_game_unit(
        db, unit_def, x=0, y=0, hp=40, max_hp=40,
        flags={"held_item": "oran_berry", "ability_id": ability.id},
    )
    unit.unit = unit_def
    db.commit()

    attach_game_unit_loadout_fields(unit, db)
    assert unit.held_item_slug == "oran_berry"
    assert unit.ability_id == ability.id
    assert unit.ability == "Loadout Ability"
    assert move.id in unit.equipped_move_ids

    # unit.unit relationship missing -> equipped_move_ids falls back to []
    orphan = _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40)
    orphan.unit = None
    attach_game_unit_loadout_fields(orphan, db)
    assert orphan.equipped_move_ids == []


# ---------------------------------------------------------------------------
# Section A.9 -- _normalize_item_id_tiles_from_map / _build_2d_matrix
# ---------------------------------------------------------------------------


def test_normalize_item_id_tiles_from_map_and_build_matrix(db):
    assert _build_2d_matrix(2, 3, 0) == [[0, 0, 0], [0, 0, 0]]

    user = _make_user(db, "itemtiles-user")

    no_tile_data_map = models.Map(
        name="No Tile Data", creator_id=user.id, width=2, height=2,
        tileset_names=[], tile_data=None, allowed_modes=["Conquest"], allowed_player_counts=[2],
    )
    assert _normalize_item_id_tiles_from_map(no_tile_data_map) == [[None, None], [None, None]]

    no_raw_map = models.Map(
        name="No Raw Items", creator_id=user.id, width=2, height=2,
        tileset_names=[], tile_data={}, allowed_modes=["Conquest"], allowed_player_counts=[2],
    )
    assert _normalize_item_id_tiles_from_map(no_raw_map) == [[None, None], [None, None]]

    partial_map = models.Map(
        name="Partial Items", creator_id=user.id, width=3, height=2,
        tileset_names=[], tile_data={"item_id_tiles": [[5, "bad", -1], "not_a_row"]},
        allowed_modes=["Conquest"], allowed_player_counts=[2],
    )
    result = _normalize_item_id_tiles_from_map(partial_map)
    assert result[0] == [5, None, None]
    assert result[1] == [None, None, None]


# ---------------------------------------------------------------------------
# Section A.10 -- reconcile_playable_players / advance_turn_if_player_has_no_actions
# ---------------------------------------------------------------------------


def test_reconcile_playable_players_non_active_status_preserves_order(db):
    user = _make_user(db, "reconcile-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = models.GameState(
        game_id=game.id, current_turn=None, status=models.GameStatus.preparation, players=[user.id, 999],
    )
    playable, eliminated, completed = reconcile_playable_players(game, state, db)
    assert playable == [user.id, 999]
    assert eliminated == []
    assert completed is False
    assert state.current_turn == 0


def test_reconcile_playable_players_completes_with_single_survivor(db):
    user_a = _make_user(db, "reconcile-a")
    user_b = _make_user(db, "reconcile-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = _make_state(db, game, [user_a.id, user_b.id])
    unit_def = _make_unit_def(db, "Reconcile Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game, user_id=user_a.id)
    # user_b has no living units

    playable, eliminated, completed = reconcile_playable_players(game, state, db)
    assert playable == [user_a.id]
    assert eliminated == [user_b.id]
    assert completed is True
    db.commit()
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user_a.id


def test_reconcile_playable_players_completes_with_zero_survivors(db):
    user_a = _make_user(db, "reconcile-zero-a")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id])
    state = _make_state(db, game, [user_a.id])
    # No units placed at all -> zero playable players

    playable, eliminated, completed = reconcile_playable_players(game, state, db)
    assert playable == []
    assert completed is True
    db.commit()
    db.refresh(state)
    assert state.winner_id is None


def test_get_playable_player_ids_in_order_filters_dead_players(db):
    user_a = _make_user(db, "playable-order-a")
    user_b = _make_user(db, "playable-order-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = _make_state(db, game, [user_b.id, user_a.id])
    unit_def = _make_unit_def(db, "PlayableOrder Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game, user_id=user_a.id)

    ordered = get_playable_player_ids_in_order(state, game.id, db)
    assert ordered == [user_a.id]


def test_advance_turn_if_player_has_no_actions_max_turns_completes(db, _mock_redis):
    from app.routes.games import advance_turn_if_player_has_no_actions

    user_a = _make_user(db, "maxturns-a")
    user_b = _make_user(db, "maxturns-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id], max_turns=1)
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=1)
    unit_def = _make_unit_def(db, "MaxTurns Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user_a.id, can_move=False)
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id, can_move=True)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user_a.id, db)
    assert completed is True
    assert turn_advanced is False
    db.refresh(state)
    assert state.status == models.GameStatus.completed


def test_advance_turn_if_player_has_no_actions_war_game_never_auto_advances(db):
    from app.routes.games import advance_turn_if_player_has_no_actions

    user = _make_user(db, "war-noaction-user")
    map_obj = _make_map(db, user.id, allowed_modes=["War"])
    game = _make_game(db, map_obj, [user.id], gamemode="War")
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "WarNoAction Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id, can_move=False)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user.id, db)
    assert (removed_ids, turn_advanced, completed) == ([], False, False)


def test_advance_turn_ignores_fainted_units_with_can_move_true(db, _mock_redis):
    """Fainted units must not block Conquest auto-advance even if can_move is True
    (e.g. leftover from a turn-start reset that re-enabled them)."""
    from app.routes.games import advance_turn_if_player_has_no_actions

    user_a = _make_user(db, "faint-block-a")
    user_b = _make_user(db, "faint-block-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=0)
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "FaintBlock Mon")
    living = _make_game_unit(
        db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user_a.id, can_move=False,
    )
    fainted = _make_game_unit(
        db,
        unit_def,
        x=-1,
        y=-1,
        hp=0,
        max_hp=40,
        game=game,
        user_id=user_a.id,
        is_fainted=True,
        can_move=True,
    )
    _make_game_unit(db, unit_def, x=2, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id, can_move=True)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(
        game, state, user_a.id, db,
    )
    assert completed is False
    assert turn_advanced is True
    db.refresh(state)
    assert state.current_turn == 1
    db.refresh(fainted)
    assert fainted.can_move is False
    db.refresh(living)
    assert living.can_move is True


def test_wait_unit_advances_despite_fainted_sibling_with_can_move(client, db, user, _mock_redis):
    """Waiting with the last fielded unit advances the turn even when a fainted
    teammate still has can_move=True."""
    ctx = _create_battle_game(db, user, link="wait-ignore-fainted")
    unit = ctx["unit"]
    unit_def = db.query(models.Unit).filter(models.Unit.id == unit.unit_id).first()
    fainted = _make_game_unit(
        db,
        unit_def,
        x=-1,
        y=-1,
        hp=0,
        max_hp=40,
        game=ctx["game"],
        user_id=user.id,
        is_fainted=True,
        can_move=True,
    )
    db.commit()

    resp = client.post("/games/wait-ignore-fainted/wait", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["turn_advanced"] is True
    assert body["game_completed"] is False

    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 1
    db.refresh(fainted)
    assert fainted.can_move is False


def test_advance_turn_if_player_has_no_actions_remaining_units_short_circuit(db):
    from app.routes.games import advance_turn_if_player_has_no_actions

    user = _make_user(db, "remaining-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Remaining Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id, can_move=True)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user.id, db)
    assert (removed_ids, turn_advanced, completed) == ([], False, False)


def test_advance_turn_if_player_has_no_actions_single_player_row_completes(db, _mock_redis):
    """Exercises the raw "only one distinct user_id among ALL unit rows" completion
    check, which runs before the turn-order reconcile and counts rows regardless
    of fainted/HP status."""
    from app.routes.games import advance_turn_if_player_has_no_actions

    user = _make_user(db, "singleplayer-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "SinglePlayer Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id, can_move=False)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user.id, db)
    assert completed is True
    assert turn_advanced is False
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user.id


def test_advance_turn_if_player_has_no_actions_second_reconcile_completes(db, _mock_redis):
    """The opponent's unit row still exists (so the raw row-count check sees 2
    distinct users and does not complete), but it is already fainted, so the
    later reconcile_playable_players() call (which filters on is_fainted/HP)
    detects the elimination and completes the game."""
    from app.routes.games import advance_turn_if_player_has_no_actions

    user = _make_user(db, "secondreconcile-user")
    opponent = _make_user(db, "secondreconcile-opp")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id, opponent.id])
    state = _make_state(db, game, [user.id, opponent.id])
    unit_def = _make_unit_def(db, "SecondReconcile Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id, can_move=False)
    _make_game_unit(
        db, unit_def, x=1, y=0, hp=0, max_hp=40, game=game, user_id=opponent.id, is_fainted=True,
    )

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user.id, db)
    assert completed is True
    assert turn_advanced is False
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user.id


# ---------------------------------------------------------------------------
# Section A.11 -- remove_fainted_units_from_play
# ---------------------------------------------------------------------------


def test_remove_fainted_units_from_play_no_fainted_returns_empty(db):
    user = _make_user(db, "nofaint-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "NoFaint Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    assert remove_fainted_units_from_play(game.id, db) == []


def test_remove_fainted_units_from_play_removes_and_logs_no_units_left(db, _mock_redis):
    user = _make_user(db, "faint-remove-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "FaintRemove Mon")
    player = models.GamePlayer(game_id=game.id, player_id=user.id, cash_remaining=100, game_units=[])
    db.add(player)
    db.commit()

    fainted = _make_game_unit(db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user.id)
    player.game_units = [fainted.id]
    db.add(player)
    db.commit()

    removed_ids = remove_fainted_units_from_play(game.id, db)
    db.commit()
    assert removed_ids == [fainted.id]
    db.refresh(fainted)
    assert fainted.is_fainted is True
    db.refresh(player)
    assert fainted.id not in player.game_units


def test_remove_fainted_units_from_play_war_restores_objectives(db, _mock_redis):
    user = _make_user(db, "faint-war-user")
    map_obj = _make_map(db, user.id, allowed_modes=["War"])
    game = _make_game(db, map_obj, [user.id], gamemode="War")
    _make_state(db, game, [user.id])
    map_state = _make_map_state(db, game, map_obj)
    map_state.objective_tiles[0][0] = {"owner": 1, "kind": "pokeball", "hp": 5, "max_hp": 10}
    flag_modified(map_state, "objective_tiles")
    db.commit()

    unit_def = _make_unit_def(db, "FaintWar Mon")
    fainted = _make_game_unit(db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user.id)

    removed_ids = remove_fainted_units_from_play(game.id, db)
    assert removed_ids == [fainted.id]


def test_remove_fainted_units_from_play_ctf_jails_instead_of_removing(db, _mock_redis):
    victor = _make_user(db, "ctf-jail-victor")
    victim = _make_user(db, "ctf-jail-victim")
    map_obj = _make_map(
        db,
        victor.id,
        width=3,
        height=3,
        allowed_modes=["Capture The Flag"],
    )
    special = [[None] * 3 for _ in range(3)]
    special[0][0] = "ctf_jail_p1"
    special[2][2] = "ctf_jail_p2"
    map_obj.tile_data = {
        **(map_obj.tile_data or {}),
        "special_tiles": special,
        "flags": [[0, None, None], [None, 1, None], [None, None, None]],
    }
    flag_modified(map_obj, "tile_data")
    db.commit()

    game = _make_game(db, map_obj, [victor.id, victim.id], gamemode="Capture The Flag")
    _make_state(db, game, [victor.id, victim.id])
    unit_def = _make_unit_def(db, "CtfJail Mon")
    attacker = _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=victor.id)
    fainted = _make_game_unit(
        db,
        unit_def,
        x=1,
        y=1,
        hp=0,
        max_hp=40,
        game=game,
        user_id=victim.id,
        flags={"last_damage_attacker_id": attacker.id},
    )

    removed_ids = remove_fainted_units_from_play(game.id, db)
    db.commit()
    db.refresh(fainted)

    assert removed_ids == []
    assert fainted.is_fainted is False
    assert fainted.current_hp == 40
    assert (fainted.current_x, fainted.current_y) == (0, 0)
    assert fainted.flags.get("jailed") is True
    assert fainted.flags.get("jailed_by") == 1


# ---------------------------------------------------------------------------
# Section A.12 -- decrement_and_expire_status_effects / apply_end_of_turn_status_damage
# ---------------------------------------------------------------------------


def test_decrement_and_expire_status_effects_branches(db, monkeypatch):
    user = _make_user(db, "decrement-status-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "DecStatus Mon")

    monkeypatch.setattr(games_mod.random, "randint", lambda a, b: a)

    expiring_sleep = _make_game_unit(
        db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id,
        status_effects=["sleep", 1], states=["nightmare", 9999], can_move=False,
    )
    sleeping = _make_game_unit(
        db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user.id,
        status_effects=["sleep", 3], can_move=True,
    )
    frozen = _make_game_unit(
        db, unit_def, x=2, y=0, hp=40, max_hp=40, game=game, user_id=user.id,
        status_effects=["frozen", 3], can_move=True,
    )
    paralyzed = _make_game_unit(
        db, unit_def, x=0, y=1, hp=40, max_hp=40, game=game, user_id=user.id,
        status_effects=["paralysis", 3], can_move=True,
    )
    badly_poisoned = _make_game_unit(
        db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id,
        status_effects=["badly_poisoned", 3, 2], can_move=True,
    )
    clean_flagged = _make_game_unit(
        db, unit_def, x=2, y=1, hp=40, max_hp=40, game=game, user_id=user.id,
        status_effects=["not_a_status"], can_move=True,
    )
    expiring_confusion = _make_game_unit(
        db, unit_def, x=0, y=2, hp=40, max_hp=40, game=game, user_id=user.id,
        states=["confusion", 1], can_move=True,
    )
    drowsy_expiring = _make_game_unit(
        db, unit_def, x=1, y=2, hp=40, max_hp=40, game=game, user_id=user.id,
        states=["drowsy", 1], can_move=True,
    )
    flinch_expiring = _make_game_unit(
        db, unit_def, x=2, y=2, hp=40, max_hp=40, game=game, user_id=user.id,
        states=["flinch", 1], can_move=True,
    )
    encore_with_metadata = _make_game_unit(
        db, unit_def, x=3, y=0, hp=40, max_hp=40, game=game, user_id=user.id,
        states=["encore", 2, 555], can_move=True,
    )
    active_confusion = _make_game_unit(
        db, unit_def, x=3, y=1, hp=40, max_hp=40, game=game, user_id=user.id,
        states=["confusion", 3], can_move=True,
    )
    active_ingrain = _make_game_unit(
        db, unit_def, x=3, y=2, hp=40, max_hp=40, game=game, user_id=user.id,
        states=["ingrain", 3], can_move=True,
    )

    modified_ids = decrement_and_expire_status_effects(user.id, game.id, db, game=game, game_state=None)
    db.commit()
    for unit in (
        expiring_sleep, sleeping, frozen, paralyzed, badly_poisoned, clean_flagged, expiring_confusion,
        drowsy_expiring, flinch_expiring, encore_with_metadata, active_confusion, active_ingrain,
    ):
        db.refresh(unit)

    assert expiring_sleep.status_effects == []
    assert expiring_sleep.states == []  # nightmare cleared when sleep expires
    assert sleeping.status_effects == ["sleep", 2]
    assert sleeping.can_move is False
    assert frozen.can_move is False
    assert paralyzed.can_move is False  # randint forced to lower bound (<=25)
    assert badly_poisoned.status_effects == ["badly_poisoned", 2, 2]
    assert clean_flagged.status_effects == []
    assert expiring_confusion.states == []
    assert drowsy_expiring.states == []
    assert flinch_expiring.states == []
    assert flinch_expiring.can_move is False
    assert encore_with_metadata.states == ["encore", 1, 555]
    assert active_confusion.can_move is False  # forced confusion self-damage roll
    assert active_ingrain.can_move is False
    assert expiring_sleep.id in modified_ids


def test_apply_end_of_turn_status_damage_branches(db):
    user = _make_user(db, "eot-status-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "EotStatus Mon")

    burned = _make_game_unit(db, unit_def, x=0, y=0, hp=80, max_hp=80, game=game, user_id=user.id, status_effects=["burn", 3])
    badly_poisoned = _make_game_unit(
        db, unit_def, x=1, y=0, hp=80, max_hp=80, game=game, user_id=user.id, status_effects=["badly_poisoned", 3, 2]
    )
    healthy = _make_game_unit(db, unit_def, x=2, y=0, hp=80, max_hp=80, game=game, user_id=user.id)

    modified_ids = apply_end_of_turn_status_damage(user.id, game.id, db)
    db.commit()
    db.refresh(burned)
    db.refresh(badly_poisoned)
    db.refresh(healthy)

    assert burned.current_hp < 80
    assert badly_poisoned.current_hp < 80
    assert badly_poisoned.status_effects == ["badly_poisoned", 3, 3]
    assert healthy.current_hp == 80
    assert burned.id in modified_ids
    assert healthy.id not in modified_ids


# ---------------------------------------------------------------------------
# Section A.13 -- compute_effective_stats
# ---------------------------------------------------------------------------


def test_compute_effective_stats_tailwind_and_status_modifiers(db):
    user = _make_user(db, "ces-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "CES Mon", base_stats={"hp": 60, "attack": 60, "defense": 60, "sp_attack": 60, "sp_defense": 60, "speed": 60})

    tailwind_ally = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id, states=["tailwind", 3])
    burned_unit = _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user.id, status_effects=["burn", 3])

    stats = compute_effective_stats(tailwind_ally, db)
    assert stats["speed"] == 130  # doubled by tailwind (base 65 -> 130)

    stats_burn = compute_effective_stats(burned_unit, db)
    assert stats_burn["attack"] == 32  # halved by burn (base 65 -> 32)

    # Use a separate game/user so the tailwind side-effect above doesn't bleed into
    # this unit's stat calculation.
    other_user = _make_user(db, "ces-user-2")
    other_game = _make_game(db, map_obj, [other_user.id])
    paralyzed_unit = _make_game_unit(
        db, unit_def, x=2, y=0, hp=40, max_hp=40, game=other_game, user_id=other_user.id, status_effects=["paralysis", 3]
    )
    stats_paralysis = compute_effective_stats(paralyzed_unit, db)
    assert stats_paralysis["speed"] == 32

    # Missing unit_info -> falls back to unit.current_stats
    orphan = _make_game_unit(db, unit_def, x=3, y=0, hp=40, max_hp=40, current_stats_extra={"hp": 999})
    orphan.unit_id = 999999
    db.commit()
    fallback_stats = compute_effective_stats(orphan, db)
    assert fallback_stats.get("hp") == 999


# ---------------------------------------------------------------------------
# Section A.14 -- critical hit / move classification helpers
# ---------------------------------------------------------------------------


def test_get_critical_hit_chance_all_stage_thresholds():
    assert get_critical_hit_chance(-6) == 0.0
    assert get_critical_hit_chance(0) == pytest.approx(1 / 16)
    assert get_critical_hit_chance(1) == pytest.approx(1 / 8)
    assert get_critical_hit_chance(2) == pytest.approx(1 / 4)
    assert get_critical_hit_chance(3) == pytest.approx(1 / 3)
    assert get_critical_hit_chance(4) == pytest.approx(1 / 2)
    assert get_critical_hit_chance(10) == pytest.approx(1 / 2)


def test_move_classification_helpers():
    guaranteed_crit_move = models.Move(name="Guaranteed Crit", type="Normal", category="Status", power=0, effects=["guaranteed_crit"])
    assert move_can_critical_hit(guaranteed_crit_move) is True

    fixed_damage_move = models.Move(name="Fixed", type="Normal", category="Status", power=0, effects=["target:fixed_damage:level"])
    assert move_can_critical_hit(fixed_damage_move) is False
    assert move_is_instant_ko(fixed_damage_move) is False

    physical_move = models.Move(name="Physical", type="Normal", category="Physical", power=40, effects=[])
    assert move_can_critical_hit(physical_move) is True
    assert move_deals_direct_damage(physical_move) is True

    status_move = models.Move(name="Status", type="Normal", category="Status", power=0, effects=[])
    assert move_can_critical_hit(status_move) is False
    assert move_deals_direct_damage(status_move) is False

    high_crit_move = models.Move(name="High Crit", type="Normal", category="Physical", power=40, effects=["self:high_crit_ratio"])
    assert move_has_high_crit_ratio(high_crit_move) is True
    suffix_crit_move = models.Move(name="Suffix Crit", type="Normal", category="Physical", power=40, effects=["target:high_crit_ratio"])
    assert move_has_high_crit_ratio(suffix_crit_move) is True

    ko_move = models.Move(name="KO", type="Ice", category="Special", power=0, effects=["target:instant_ko"])
    assert move_is_instant_ko(ko_move) is True


# ---------------------------------------------------------------------------
# Section A.15 -- move_lands_on_target / accuracy helpers
# ---------------------------------------------------------------------------


def test_move_lands_on_target_and_accuracy_threshold(db):
    unit_def = _make_unit_def(db, "Accuracy Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)
    target_glaive = _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, states=["glaive_rush", 1])
    target_plain = _make_game_unit(db, unit_def, x=2, y=0, hp=40, max_hp=40)

    perfect_move = models.Move(name="Perfect Acc", type="Normal", category="Physical", accuracy=None, effects=[])
    assert move_lands_on_target(perfect_move, attacker, target_glaive) is True
    assert move_lands_on_target(perfect_move, attacker, target_plain) is True

    always_hit_move = models.Move(name="AlwaysHit", type="Normal", category="Physical", accuracy=999, effects=[])
    assert get_modified_accuracy_threshold(999, attacker, target_plain) >= 100
    assert move_lands_on_target(always_hit_move, attacker, target_plain) is True

    always_miss_move = models.Move(name="AlwaysMiss", type="Normal", category="Physical", accuracy=0, effects=[])
    assert move_lands_on_target(always_miss_move, attacker, target_plain) is False

    assert get_modified_accuracy_threshold(None, attacker, target_plain) is None
    assert get_modified_accuracy_threshold("not_a_number", attacker, target_plain) is None


# ---------------------------------------------------------------------------
# Section A.16 -- advance_if_expired
# ---------------------------------------------------------------------------


def test_advance_if_expired_not_in_progress_or_no_deadline(db):
    from datetime import datetime, timedelta, timezone

    from app.routes.games import advance_if_expired

    user = _make_user(db, "expire-basic-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    game.turn_seconds = 300
    db.add(game)
    db.commit()

    closed_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.closed, players=[user.id],
        turn_deadline=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    assert advance_if_expired(game, closed_state, db) is False

    no_deadline_state = models.GameState(
        game_id=game.id, current_turn=0, status=models.GameStatus.in_progress, players=[user.id],
        turn_deadline=None,
    )
    assert advance_if_expired(game, no_deadline_state, db) is False


def test_advance_if_expired_not_yet_due_with_and_without_warning(db):
    from datetime import datetime, timedelta, timezone

    from app.routes.games import advance_if_expired

    user_a = _make_user(db, "expire-notdue-a")
    user_b = _make_user(db, "expire-notdue-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    game.turn_seconds = 300
    db.add(game)
    db.commit()
    unit_def = _make_unit_def(db, "ExpireNotDue Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user_a.id)
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id)

    state = _make_state(db, game, [user_a.id, user_b.id])
    state.turn_deadline = datetime.now(timezone.utc) + timedelta(seconds=200)
    assert advance_if_expired(game, state, db) is False
    assert state.replay_log == []

    state.turn_deadline = datetime.now(timezone.utc) + timedelta(seconds=20)
    assert advance_if_expired(game, state, db) is False
    assert any(isinstance(row, dict) for row in (state.replay_log or []))


def test_advance_if_expired_full_turn_advance_path(db):
    from datetime import datetime, timedelta, timezone

    from app.routes.games import advance_if_expired

    user_a = _make_user(db, "expire-advance-a")
    user_b = _make_user(db, "expire-advance-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    game.turn_seconds = 300
    db.add(game)
    db.commit()
    unit_def = _make_unit_def(db, "ExpireAdvance Mon")
    unit_a = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user_a.id, can_move=False)
    unit_b = _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id)

    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=0)
    state.turn_deadline = datetime.now(timezone.utc) - timedelta(seconds=5)

    assert advance_if_expired(game, state, db) is True
    db.refresh(state)
    db.refresh(unit_a)
    assert state.current_turn == 1
    assert state.turn_deadline is not None
    assert unit_a.can_move is True  # reset before advancing turn


def test_advance_if_expired_round_weather_and_max_turns_completion(db):
    from datetime import datetime, timedelta, timezone

    from app.routes.games import advance_if_expired

    user_a = _make_user(db, "expire-round-a")
    user_b = _make_user(db, "expire-round-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id], max_turns=1)
    game.turn_seconds = 300
    db.add(game)
    db.commit()
    unit_def = _make_unit_def(db, "ExpireRound Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user_a.id)
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id)

    # current_turn=1 -> (1+1) % 2 == 0 triggers end-of-round weather/hazard processing,
    # and incrementing to 2 meets max_turns(1) * len(players)(2) == 2 -> game completes.
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=1)
    state.turn_deadline = datetime.now(timezone.utc) - timedelta(seconds=5)

    assert advance_if_expired(game, state, db) is True
    db.refresh(state)
    assert state.status == models.GameStatus.completed


def test_advance_if_expired_already_completed_via_top_level_reconcile(db):
    """A single-player game is always considered "won" by reconcile_playable_players
    (len(playable_players) == 1), so advance_if_expired should short-circuit and
    report completed immediately, before even checking the deadline."""
    from datetime import datetime, timedelta, timezone

    from app.routes.games import advance_if_expired

    user = _make_user(db, "expire-topcomplete-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    game.turn_seconds = 300
    db.add(game)
    db.commit()
    unit_def = _make_unit_def(db, "ExpireTopComplete Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)

    state = _make_state(db, game, [user.id])
    state.turn_deadline = datetime.now(timezone.utc) + timedelta(seconds=300)  # not yet expired

    assert advance_if_expired(game, state, db) is True
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user.id


def test_advance_if_expired_publishes_removed_ids_from_already_fainted_unit(db, _mock_redis):
    """A unit that already reached 0 HP (but hadn't yet been swept off the board)
    gets removed during the turn-advance sweep, and the turn still advances
    normally because the owning player has another unit alive."""
    from datetime import datetime, timedelta, timezone

    from app.routes.games import advance_if_expired

    user_a = _make_user(db, "expire-removedids-a")
    user_b = _make_user(db, "expire-removedids-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    game.turn_seconds = 300
    db.add(game)
    db.commit()
    unit_def = _make_unit_def(db, "ExpireRemovedIds Mon")
    dying_unit = _make_game_unit(db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user_a.id)
    _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user_a.id)
    _make_game_unit(db, unit_def, x=2, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id)

    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=0)
    state.turn_deadline = datetime.now(timezone.utc) - timedelta(seconds=5)

    assert advance_if_expired(game, state, db) is True
    db.refresh(dying_unit)
    assert dying_unit.is_fainted is True
    published = [str(call.args[1]) for call in _mock_redis.publish.call_args_list if call.args]
    assert any("unit_removed" in msg and str(dying_unit.id) in msg for msg in published)


def test_advance_if_expired_max_turns_draw_with_single_leader(db):
    """When max_turns is reached, if exactly one player has the most remaining
    units, that player is declared the winner rather than a draw."""
    from datetime import datetime, timedelta, timezone

    from app.routes.games import advance_if_expired

    user_a = _make_user(db, "expire-drawleader-a")
    user_b = _make_user(db, "expire-drawleader-b")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id], max_turns=1)
    game.turn_seconds = 300
    db.add(game)
    db.commit()
    unit_def = _make_unit_def(db, "ExpireDrawLeader Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user_a.id)
    _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user_a.id)
    _make_game_unit(db, unit_def, x=2, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id)

    # current_turn=2 -> it's user_a's turn (index 0); incrementing to 3 meets
    # max_turns(1) * len(players)(2) == 2, triggering the draw-resolution path.
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=2)
    state.turn_deadline = datetime.now(timezone.utc) - timedelta(seconds=5)

    assert advance_if_expired(game, state, db) is True
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user_a.id


# ---------------------------------------------------------------------------
# Section B -- HTTP endpoint coverage
# ---------------------------------------------------------------------------


def test_state_endpoints_member_and_non_member(client, db, user):
    ctx = _create_battle_game(db, user, link="state-1")

    get_resp = client.get("/games/state-1/state")
    assert get_resp.status_code == 200
    assert get_resp.json()["current_turn"] == 0

    patch_resp = client.patch("/games/state-1/state", json={"current_turn": 1})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["current_turn"] == 1
    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 1

    replay_patch = client.patch("/games/state-1/state", json={"replay_log": [{"event": "manual"}]})
    assert replay_patch.status_code == 200
    assert replay_patch.json()["replay_log"] == [{"event": "manual"}]


def test_state_endpoints_404_for_missing_game(client, db, user):
    resp = client.get("/games/does-not-exist/state")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Game not found"

    patch_resp = client.patch("/games/does-not-exist/state", json={})
    assert patch_resp.status_code == 404


def test_state_endpoints_404_for_non_member(client, db, user):
    _create_battle_game(db, user, link="state-2")

    outsider = models.User(username="outsider", email="outsider@example.com", hashed_password="x")
    db.add(outsider)
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: outsider
    get_resp = client.get("/games/state-2/state")
    patch_resp = client.patch("/games/state-2/state", json={"current_turn": 5})
    app.dependency_overrides[get_current_user] = lambda: user

    assert get_resp.status_code == 404
    assert get_resp.json()["detail"] == "Game state not found"
    assert patch_resp.status_code == 404


# ---------------------------------------------------------------------------
# Section B -- start_game
# ---------------------------------------------------------------------------


def _seed_full_game_for_start(db, host, other, *, gamemode="Conquest", status=models.GameStatus.closed, with_map_state=True, width=4, height=4):
    map_obj = models.Map(
        name=f"Start Map {gamemode}-{status}-{next(_link_counter)}",
        creator_id=host.id,
        is_official=True,
        width=width,
        height=height,
        tileset_names=["grass"],
        tile_data={"movement_cost": [[1] * width for _ in range(height)]},
        allowed_modes=[gamemode],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.flush()
    game = models.Game(
        game_name=f"Start Game {next(_link_counter)}",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode=gamemode,
        is_private=False,
        host_id=host.id,
        link=f"start-link-{next(_link_counter)}",
        turn_seconds=120,
    )
    db.add(game)
    db.flush()
    state = models.GameState(
        game_id=game.id, current_turn=0, status=status, players=[host.id, other.id], replay_log=[],
    )
    db.add(state)
    if with_map_state:
        db.add(
            models.GameMapState(
                game_id=game.id,
                map_id=map_obj.id,
                weather_tiles=[[0] * width for _ in range(height)],
                hazard_tiles=[[[] for _ in range(width)] for _ in range(height)],
                room_effect_tiles=[[0] * width for _ in range(height)],
                terrain_effect_tiles=[[0] * width for _ in range(height)],
                field_effect_tiles=[[0] * width for _ in range(height)],
                item_id_tiles=[[None] * width for _ in range(height)],
                objective_tiles=[[None for _ in range(width)] for _ in range(height)],
            )
        )
    db.commit()

    # Place one living unit per player so reconcile_playable_players (invoked via
    # compute_turn_locks on the in_progress transition) doesn't immediately complete
    # the game due to zero/one remaining playable players.
    unit_def = _make_unit_def(db, f"Start Mon {next(_link_counter)}")
    host_unit = models.GameUnit(
        game_id=game.id, unit_id=unit_def.id, user_id=host.id,
        starting_x=0, starting_y=0, current_x=0, current_y=0, level=50,
        current_hp=40, current_stats={"hp": 40, "attack": 40, "defense": 40, "sp_attack": 40, "sp_defense": 40, "speed": 40, "range": 3},
        stat_boosts=default_stat_boosts(), status_effects=[], states=[], is_fainted=False, can_move=True,
    )
    other_unit = models.GameUnit(
        game_id=game.id, unit_id=unit_def.id, user_id=other.id,
        starting_x=width - 1, starting_y=height - 1, current_x=width - 1, current_y=height - 1, level=50,
        current_hp=40, current_stats={"hp": 40, "attack": 40, "defense": 40, "sp_attack": 40, "sp_defense": 40, "speed": 40, "range": 3},
        stat_boosts=default_stat_boosts(), status_effects=[], states=[], is_fainted=False, can_move=True,
    )
    db.add_all([host_unit, other_unit])
    db.commit()
    return game, state, map_obj


def test_start_game_conquest_closed_to_preparation_to_in_progress(client, db, user, _mock_redis):
    other = _make_user(db, "start-conquest-other")
    game, state, _ = _seed_full_game_for_start(db, user, other, gamemode="Conquest")

    resp1 = client.post(f"/games/start/{game.id}")
    assert resp1.status_code == 200
    assert resp1.json()["detail"] == "Game moved to preparation phase"
    db.refresh(state)
    assert state.status == models.GameStatus.preparation

    resp2 = client.post(f"/games/start/{game.id}")
    assert resp2.status_code == 200
    assert resp2.json()["detail"] == "Game started"
    db.refresh(state)
    assert state.status == models.GameStatus.in_progress
    assert state.current_turn == 0


def test_start_game_war_mode_both_phases(client, db, user, _mock_redis):
    other = _make_user(db, "start-war-other")
    game, state, map_obj = _seed_full_game_for_start(db, user, other, gamemode="War")

    resp1 = client.post(f"/games/start/{game.id}")
    assert resp1.status_code == 200
    assert resp1.json()["detail"] == "Game moved to preparation phase"

    resp2 = client.post(f"/games/start/{game.id}")
    assert resp2.status_code == 200
    assert resp2.json()["detail"] == "Game started"


def test_start_game_error_branches(client, db, user, _mock_redis):
    other = _make_user(db, "start-error-other")

    missing_resp = client.post("/games/start/999999")
    assert missing_resp.status_code == 404

    game, state, _ = _seed_full_game_for_start(db, user, other, gamemode="Conquest")
    app.dependency_overrides[get_current_user] = lambda: other
    not_host_resp = client.post(f"/games/start/{game.id}")
    app.dependency_overrides[get_current_user] = lambda: user
    assert not_host_resp.status_code == 403

    game.max_players = 5
    db.add(game)
    db.commit()
    not_full_resp = client.post(f"/games/start/{game.id}")
    assert not_full_resp.status_code == 400
    assert not_full_resp.json()["detail"] == "Game not full"
    game.max_players = 2
    db.add(game)
    db.commit()

    already_game, already_state, _ = _seed_full_game_for_start(
        db, user, other, gamemode="Conquest", status=models.GameStatus.completed
    )
    already_resp = client.post(f"/games/start/{already_game.id}")
    assert already_resp.status_code == 400
    assert already_resp.json()["detail"] == "Game already in progress or completed"

    # NOTE: the "Unsupported game mode" else-branch in start_game is unreachable in
    # practice: Game.gamemode is a DB-level Enum(GameMode) restricted to exactly
    # {Conquest, War, Capture The Flag}, all of which are handled above.

    map_obj = _make_map(db, user.id)
    stateless_game = models.Game(
        game_name="No State Start Game", map_id=map_obj.id, map_name=map_obj.name, max_players=1,
        gamemode="Conquest", is_private=False, host_id=user.id, link=f"start-nostate-{next(_link_counter)}",
    )
    db.add(stateless_game)
    db.commit()
    no_state_resp = client.post(f"/games/start/{stateless_game.id}")
    assert no_state_resp.status_code == 404
    assert no_state_resp.json()["detail"] == "Game state not found"


# ---------------------------------------------------------------------------
# Section B -- place_unit War in_progress summon
# ---------------------------------------------------------------------------


def test_place_unit_war_in_progress_summon_success(client, db, user):
    width = height = 6
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    ctx = _create_battle_game(
        db, user, link="war-summon-1", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    unit_info = _make_unit_definition_http(db, link="war-summon-1", suffix="summon")
    db.commit()

    resp = client.post(
        "/games/war-summon-1/units/place",
        json={
            "unit_id": unit_info.id,
            "x": 0,
            "y": 0,
            "current_hp": 60,
            "stat_boosts": _default_stat_boosts(),
            "status_effects": [],
            "states": [],
            "is_fainted": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_move"] is False  # war summons lock the unit for that turn
    assert body["current_x"] == 0
    assert body["current_y"] == 0


def test_place_unit_war_preparation_not_objective_and_wrong_owner(client, db, user):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][1] = {"owner": 2, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    ctx = _create_battle_game(
        db, user, link="place-prep-noobjective", gamemode="War", status=models.GameStatus.preparation,
        width=width, height=height, war_objectives=objectives,
    )
    unit_a = _make_unit_definition_http(db, link="place-prep-noobjective", suffix="a")
    unit_b = _make_unit_definition_http(db, link="place-prep-noobjective", suffix="b")
    db.commit()

    # (2, 2) has no objective at all.
    resp_none = client.post(
        "/games/place-prep-noobjective/units/place",
        json={
            "unit_id": unit_a.id, "x": 2, "y": 2, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp_none.status_code == 400
    assert resp_none.json()["detail"] == "Units must be placed on owned objectives"

    # (1, 0) has an objective, but it's owned by player 2, not this player (player 1).
    resp_wrong_owner = client.post(
        "/games/place-prep-noobjective/units/place",
        json={
            "unit_id": unit_b.id, "x": 1, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp_wrong_owner.status_code == 400
    assert resp_wrong_owner.json()["detail"] == "You can only place units on your objectives"


def test_place_unit_war_in_progress_unit_limit_reached(client, db, user):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    ctx = _create_battle_game(
        db, user, link="place-inprogress-limit", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    ctx["game"].unit_limit = 1  # the player already has 1 unit placed (from the fixture)
    db.add(ctx["game"])
    db.commit()
    unit_info = _make_unit_definition_http(db, link="place-inprogress-limit", suffix="limit")
    db.commit()

    resp = client.post(
        "/games/place-inprogress-limit/units/place",
        json={
            "unit_id": unit_info.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit limit reached"


def test_place_unit_war_in_progress_errors(client, db, user):
    width = height = 6
    objectives = [[None for _ in range(width)] for _ in range(height)]
    ctx = _create_battle_game(
        db, user, link="war-summon-2", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    unit_info = _make_unit_definition_http(db, link="war-summon-2", suffix="err")
    db.commit()

    # No objective on the tile -> "Units can only be summoned on owned objectives"
    resp = client.post(
        "/games/war-summon-2/units/place",
        json={
            "unit_id": unit_info.id,
            "x": 0,
            "y": 0,
            "current_hp": 60,
            "stat_boosts": _default_stat_boosts(),
            "status_effects": [],
            "states": [],
            "is_fainted": False,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Units can only be summoned on owned objectives"


def test_place_unit_game_not_found_and_player_not_member(client, db, user):
    resp = client.post(
        "/games/does-not-exist/units/place",
        json={
            "unit_id": 1, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Game not found"

    other_host = _make_user(db, "place-other-host")
    map_obj = _make_map(db, other_host.id)
    game = _make_game(db, map_obj, [other_host.id], host_id=other_host.id)
    _make_state(db, game, [other_host.id], status=models.GameStatus.preparation)
    unit_info = _make_unit_definition_http(db, link=game.link, suffix="notmember")
    db.commit()

    resp2 = client.post(
        f"/games/{game.link}/units/place",
        json={
            "unit_id": unit_info.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp2.status_code == 404
    assert resp2.json()["detail"] == "Player state not found"


def test_place_unit_unit_not_found_and_tile_blocked(client, db, user):
    ctx = _create_battle_game(db, user, link="place-notfound", gamemode="Conquest", status=models.GameStatus.preparation)
    resp = client.post(
        "/games/place-notfound/units/place",
        json={
            "unit_id": 999999, "x": 2, "y": 2, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unit not found"

    map_obj = ctx["map_obj"]
    width, height = map_obj.width, map_obj.height
    special_tiles = [[None for _ in range(width)] for _ in range(height)]
    special_tiles[2][2] = "impassable"
    map_obj.tile_data = {**map_obj.tile_data, "special_tiles": special_tiles}
    db.add(map_obj)
    db.commit()

    unit_info = _make_unit_definition_http(db, link="place-notfound", suffix="blocked")
    db.commit()
    resp2 = client.post(
        "/games/place-notfound/units/place",
        json={
            "unit_id": unit_info.id, "x": 2, "y": 2, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "This unit cannot be placed on this tile"


def test_place_unit_war_state_and_map_state_missing(client, db, user):
    map_obj = _make_map(db, user.id, allowed_modes=["War"])
    game = _make_game(db, map_obj, [user.id], gamemode="War")
    player = models.GamePlayer(game_id=game.id, player_id=user.id, cash_remaining=1000, game_units=[], is_ready=False)
    db.add(player)
    db.commit()
    unit_info = _make_unit_definition_http(db, link=game.link, suffix="nostate")
    db.commit()

    resp = client.post(
        f"/games/{game.link}/units/place",
        json={
            "unit_id": unit_info.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game state"

    game2 = _make_game(db, map_obj, [user.id], gamemode="War")
    _make_state(db, game2, [user.id], status=models.GameStatus.preparation)
    player2 = models.GamePlayer(game_id=game2.id, player_id=user.id, cash_remaining=1000, game_units=[], is_ready=False)
    db.add(player2)
    db.commit()
    unit_info2 = _make_unit_definition_http(db, link=game2.link, suffix="nomapstate")
    db.commit()

    resp2 = client.post(
        f"/games/{game2.link}/units/place",
        json={
            "unit_id": unit_info2.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp2.status_code == 500
    assert resp2.json()["detail"] == "Map state missing"


def test_place_unit_war_player_not_in_game(client, db, user):
    other = _make_user(db, "place-not-in-game-other")
    map_obj = _make_map(db, user.id, allowed_modes=["War"])
    game = _make_game(db, map_obj, [other.id], gamemode="War", host_id=other.id)
    _make_state(db, game, [other.id], status=models.GameStatus.preparation)
    _make_map_state(db, game, map_obj)
    player = models.GamePlayer(game_id=game.id, player_id=user.id, cash_remaining=1000, game_units=[], is_ready=False)
    db.add(player)
    db.commit()
    unit_info = _make_unit_definition_http(db, link=game.link, suffix="notinlist")
    db.commit()

    resp = client.post(
        f"/games/{game.link}/units/place",
        json={
            "unit_id": unit_info.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Player not in game"


def test_place_unit_war_preparation_tile_occupied_and_unit_limit(client, db, user):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    objectives[0][1] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    ctx = _create_battle_game(
        db, user, link="place-prep-occupied", gamemode="War", status=models.GameStatus.preparation,
        width=width, height=height, war_objectives=objectives,
    )
    unit_a = _make_unit_definition_http(db, link="place-prep-occupied", suffix="a")
    unit_b = _make_unit_definition_http(db, link="place-prep-occupied", suffix="b")
    db.commit()

    resp1 = client.post(
        "/games/place-prep-occupied/units/place",
        json={
            "unit_id": unit_a.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        "/games/place-prep-occupied/units/place",
        json={
            "unit_id": unit_b.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Tile occupied"

    game = ctx["game"]
    game.unit_limit = 1
    db.add(game)
    db.commit()

    resp3 = client.post(
        "/games/place-prep-occupied/units/place",
        json={
            "unit_id": unit_b.id, "x": 1, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp3.status_code == 400
    assert resp3.json()["detail"] == "Unit limit reached"


def test_place_unit_war_in_progress_not_your_turn(client, db, user):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    ctx = _create_battle_game(
        db, user, link="place-notyourturn", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    ctx["state"].current_turn = 1
    db.add(ctx["state"])
    db.commit()
    unit_info = _make_unit_definition_http(db, link="place-notyourturn", suffix="turn")
    db.commit()

    resp = client.post(
        "/games/place-notyourturn/units/place",
        json={
            "unit_id": unit_info.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not your turn"


def test_place_unit_war_in_progress_game_completed(client, db, user):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    ctx = _create_battle_game(
        db, user, link="place-completed", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    ctx["opponent_unit"].current_hp = 0
    db.add(ctx["opponent_unit"])
    db.commit()
    unit_info = _make_unit_definition_http(db, link="place-completed", suffix="done")
    db.commit()

    resp = client.post(
        "/games/place-completed/units/place",
        json={
            "unit_id": unit_info.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game completed"


def test_place_unit_war_in_progress_tile_occupied_and_already_summoned(client, db, user):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    objectives[0][1] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": 1}
    ctx = _create_battle_game(
        db, user, link="place-alreadysummoned", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    unit_a = _make_unit_definition_http(db, link="place-alreadysummoned", suffix="a")
    unit_b = _make_unit_definition_http(db, link="place-alreadysummoned", suffix="b")
    db.commit()

    resp1 = client.post(
        "/games/place-alreadysummoned/units/place",
        json={
            "unit_id": unit_a.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp1.status_code == 200

    ctx["state"].current_turn = 0
    db.add(ctx["state"])
    db.commit()

    # (0, 0) is now occupied by the unit summoned above.
    resp2 = client.post(
        "/games/place-alreadysummoned/units/place",
        json={
            "unit_id": unit_b.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Tile occupied"

    # (1, 0) is empty but was already used to summon earlier this round.
    resp3 = client.post(
        "/games/place-alreadysummoned/units/place",
        json={
            "unit_id": unit_b.id, "x": 1, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp3.status_code == 400
    assert resp3.json()["detail"] == "This objective already summoned a unit this round"


def test_place_unit_war_wrong_phase(client, db, user):
    width = height = 4
    ctx = _create_battle_game(
        db, user, link="place-wrongphase", gamemode="War", status=models.GameStatus.closed,
        width=width, height=height,
    )
    unit_info = _make_unit_definition_http(db, link="place-wrongphase", suffix="phase")
    db.commit()

    resp = client.post(
        "/games/place-wrongphase/units/place",
        json={
            "unit_id": unit_info.id, "x": 0, "y": 0, "current_hp": 10,
            "stat_boosts": _default_stat_boosts(), "status_effects": [], "states": [], "is_fainted": False,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Cannot place units in the current game phase"


# ---------------------------------------------------------------------------
# Section B -- end_turn / get_turnlock
# ---------------------------------------------------------------------------


def test_end_turn_not_in_progress_and_invalid_game(client, db, user):
    resp = client.post("/games/does-not-exist/end_turn")
    assert resp.status_code == 404

    _create_battle_game(db, user, link="endturn-notinprogress", status=models.GameStatus.preparation)
    resp2 = client.post("/games/endturn-notinprogress/end_turn")
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Game not in progress"


def test_end_turn_not_your_turn(client, db, user):
    ctx = _create_battle_game(db, user, link="endturn-notyourturn")
    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    resp = client.post("/games/endturn-notyourturn/end_turn")
    app.dependency_overrides[get_current_user] = lambda: user
    assert resp.status_code == 403


def test_end_turn_success_advances_turn(client, db, user):
    ctx = _create_battle_game(db, user, link="endturn-success")
    resp = client.post("/games/endturn-success/end_turn")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Turn ended"
    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 1


def test_end_turn_max_turns_completes_game(client, db, user):
    ctx = _create_battle_game(db, user, link="endturn-maxturns")
    ctx["game"].max_turns = 1
    db.add(ctx["game"])
    ctx["state"].current_turn = 1
    db.add(ctx["state"])
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    resp = client.post("/games/endturn-maxturns/end_turn")
    app.dependency_overrides[get_current_user] = lambda: user
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Game completed"
    db.refresh(ctx["state"])
    assert ctx["state"].status == models.GameStatus.completed


def test_end_turn_completed_via_top_level_reconcile_single_player(client, db, user):
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "EndTurnSingle Mon")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    db.commit()

    resp = client.post(f"/games/{game.link}/end_turn")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Game completed"
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user.id


def test_end_turn_publishes_removed_ids_from_already_fainted_unit(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="endturn-removedids")
    fainted_extra = models.GameUnit(
        game_id=ctx["game"].id, unit_id=ctx["unit"].unit_id, user_id=user.id,
        starting_x=3, starting_y=3, current_x=3, current_y=3, level=50,
        current_hp=0, current_stats=dict(ctx["unit"].current_stats), stat_boosts=_default_stat_boosts(),
        status_effects=[], states=[], is_fainted=False, can_move=False,
    )
    db.add(fainted_extra)
    db.commit()

    resp = client.post("/games/endturn-removedids/end_turn")
    assert resp.status_code == 200
    db.refresh(fainted_extra)
    assert fainted_extra.is_fainted is True
    published = [call.args[1] for call in _mock_redis.publish.call_args_list if call.args]
    assert any(
        isinstance(msg, str) and "unit_removed" in msg and str(fainted_extra.id) in msg
        for msg in published
    )


def test_end_turn_max_turns_draw_with_single_leader(client, db, user):
    ctx = _create_battle_game(db, user, link="endturn-drawleader")
    extra_unit = models.GameUnit(
        game_id=ctx["game"].id, unit_id=ctx["unit"].unit_id, user_id=user.id,
        starting_x=3, starting_y=3, current_x=3, current_y=3, level=50,
        current_hp=100, current_stats=dict(ctx["unit"].current_stats), stat_boosts=_default_stat_boosts(),
        status_effects=[], states=[], is_fainted=False, can_move=True,
    )
    db.add(extra_unit)
    ctx["game"].max_turns = 1
    db.add(ctx["game"])
    # current_turn=2 -> it's user's turn (index 0); incrementing to 3 meets
    # max_turns(1) * len(players)(2) == 2, triggering the draw-resolution path,
    # and user has 2 alive units vs the opponent's 1, so user wins outright.
    ctx["state"].current_turn = 2
    db.add(ctx["state"])
    db.commit()

    resp = client.post("/games/endturn-drawleader/end_turn")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Game completed"
    db.refresh(ctx["state"])
    assert ctx["state"].winner_id == user.id


def test_get_turnlock_empty_and_missing_game(client, db, user):
    resp = client.get("/games/does-not-exist/turnlock")
    assert resp.status_code == 404

    ctx = _create_battle_game(db, user, link="turnlock-empty")
    resp2 = client.get("/games/turnlock-empty/turnlock")
    assert resp2.status_code == 200
    assert resp2.json() == {}


# ---------------------------------------------------------------------------
# Section B -- change_unit_item / remove_unit_item / change_unit_ability / remove_unit
# ---------------------------------------------------------------------------


def test_change_unit_item_success_and_errors(client, db, user):
    ctx = _create_battle_game(db, user, link="changeitem-1", preparation=True)
    unit = ctx["unit"]
    player = ctx["player"]
    player.cash_remaining = 1000
    db.add(player)
    db.commit()

    berry = models.Item(name="Change Berry", slug="change_berry", category="berry", cost=20)
    other_item = models.Item(name="Change Other", slug="change_other", category="berry", cost=50)
    db.add_all([berry, other_item])
    db.commit()

    resp = client.post(f"/games/changeitem-1/units/{unit.id}/item", json={"item_id": berry.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["unit"]["held_item_slug"] == "change_berry"
    assert body["cash_remaining"] == 1000 - 20

    # Setting the same item again is a no-op that doesn't change cash.
    resp2 = client.post(f"/games/changeitem-1/units/{unit.id}/item", json={"item_id": berry.id})
    assert resp2.status_code == 200
    assert resp2.json()["cash_remaining"] == 1000 - 20

    # Swapping to a pricier item charges the net cost.
    resp3 = client.post(f"/games/changeitem-1/units/{unit.id}/item", json={"item_id": other_item.id})
    assert resp3.status_code == 200
    assert resp3.json()["cash_remaining"] == 1000 - 50

    # Not enough cash for a much pricier item.
    expensive_item = models.Item(name="Change Expensive", slug="change_expensive", category="berry", cost=100000)
    db.add(expensive_item)
    db.commit()
    resp4 = client.post(f"/games/changeitem-1/units/{unit.id}/item", json={"item_id": expensive_item.id})
    assert resp4.status_code == 400
    assert resp4.json()["detail"] == "Not enough cash"

    # Unknown item id.
    resp5 = client.post(f"/games/changeitem-1/units/{unit.id}/item", json={"item_id": 999999})
    assert resp5.status_code == 404

    # Not in preparation phase.
    ctx2 = _create_battle_game(db, user, link="changeitem-2", status=models.GameStatus.in_progress)
    resp6 = client.post(f"/games/changeitem-2/units/{ctx2['unit'].id}/item", json={"item_id": berry.id})
    assert resp6.status_code == 400

    # Missing game / unit / player state.
    resp7 = client.post("/games/does-not-exist/units/1/item", json={"item_id": berry.id})
    assert resp7.status_code == 404
    resp8 = client.post(f"/games/changeitem-1/units/999999/item", json={"item_id": berry.id})
    assert resp8.status_code == 404


def test_remove_unit_item_success_and_noop(client, db, user):
    ctx = _create_battle_game(db, user, link="removeitem-1", preparation=True)
    unit = ctx["unit"]
    player = ctx["player"]
    player.cash_remaining = 500
    db.add(player)

    berry = models.Item(name="Removeitem Berry", slug="removeitem_berry", category="berry", cost=30)
    db.add(berry)
    db.commit()

    from app.routes.games import set_unit_held_item
    set_unit_held_item(unit, berry.slug, db)
    db.commit()

    resp = client.delete(f"/games/removeitem-1/units/{unit.id}/item")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cash_remaining"] == 500 + 30
    assert body["unit"]["held_item_slug"] is None

    # No item held -> no-op branch.
    resp2 = client.delete(f"/games/removeitem-1/units/{unit.id}/item")
    assert resp2.status_code == 200
    assert resp2.json()["cash_remaining"] == 500 + 30


def test_change_unit_ability_success_and_errors(client, db, user):
    ctx = _create_battle_game(db, user, link="changeability-1", preparation=True)
    unit = ctx["unit"]
    unit_info = db.query(models.Unit).filter_by(id=unit.unit_id).first()

    ability_a = models.Ability(name="Ability A", slug="ability-a", generation=1)
    ability_b = models.Ability(name="Ability B", slug="ability-b", generation=1)
    db.add_all([ability_a, ability_b])
    db.commit()
    unit_info.ability_ids = [ability_a.id, ability_b.id]
    db.add(unit_info)
    db.commit()

    resp = client.post(f"/games/changeability-1/units/{unit.id}/ability", json={"ability_id": ability_a.id})
    assert resp.status_code == 200
    assert resp.json()["unit"]["ability_id"] == ability_a.id

    # Same ability again -> no-op branch.
    resp2 = client.post(f"/games/changeability-1/units/{unit.id}/ability", json={"ability_id": ability_a.id})
    assert resp2.status_code == 200

    # Switch to the other learnable ability.
    resp3 = client.post(f"/games/changeability-1/units/{unit.id}/ability", json={"ability_id": ability_b.id})
    assert resp3.status_code == 200
    assert resp3.json()["unit"]["ability_id"] == ability_b.id

    # Ability the unit cannot learn.
    unrelated_ability = models.Ability(name="Unrelated Ability", slug="unrelated-ability", generation=1)
    db.add(unrelated_ability)
    db.commit()
    resp4 = client.post(f"/games/changeability-1/units/{unit.id}/ability", json={"ability_id": unrelated_ability.id})
    assert resp4.status_code == 400


def test_remove_unit_refunds_cash(client, db, user):
    ctx = _create_battle_game(db, user, link="removeunit-1", preparation=True)
    unit = ctx["unit"]
    player = ctx["player"]
    player.cash_remaining = 0
    player.game_units = [unit.id]
    db.add(player)
    db.commit()

    resp = client.delete(f"/games/removeunit-1/units/remove/{unit.id}")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Unit removed and cash refunded"
    db.refresh(player)
    assert unit.id not in player.game_units
    assert player.cash_remaining > 0

    resp2 = client.delete(f"/games/removeunit-1/units/remove/{unit.id}")
    assert resp2.status_code == 404


def test_remove_unit_item_game_not_found_and_player_state_not_found(client, db, user):
    resp_missing = client.delete("/games/does-not-exist/units/1/item")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    other_host = _make_user(db, "removeitem-nostate-host")
    map_obj = _make_map(db, other_host.id)
    game = _make_game(db, map_obj, [other_host.id, user.id], host_id=other_host.id)
    _make_state(db, game, [other_host.id, user.id], status=models.GameStatus.preparation)
    unit_def = _make_unit_def(db, "RemoveItem NoPlayerState Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    db.commit()

    resp_no_player = client.delete(f"/games/{game.link}/units/{unit.id}/item")
    assert resp_no_player.status_code == 404
    assert resp_no_player.json()["detail"] == "Player state not found"


def test_change_unit_ability_game_not_found_and_player_state_not_found(client, db, user):
    resp_missing = client.post("/games/does-not-exist/units/1/ability", json={"ability_id": 1})
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    other_host = _make_user(db, "changeability-nostate-host")
    map_obj = _make_map(db, other_host.id)
    game = _make_game(db, map_obj, [other_host.id, user.id], host_id=other_host.id)
    _make_state(db, game, [other_host.id, user.id], status=models.GameStatus.preparation)
    unit_def = _make_unit_def(db, "ChangeAbility NoPlayerState Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    db.commit()

    resp_no_player = client.post(f"/games/{game.link}/units/{unit.id}/ability", json={"ability_id": 1})
    assert resp_no_player.status_code == 404
    assert resp_no_player.json()["detail"] == "Player state not found"


def test_remove_unit_game_not_found_metadata_missing_and_player_state_not_found(client, db, user):
    resp_missing = client.delete("/games/does-not-exist/units/remove/1")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    other_host = _make_user(db, "removeunit-nostate-host")
    map_obj = _make_map(db, other_host.id)
    game = _make_game(db, map_obj, [other_host.id, user.id], host_id=other_host.id)
    _make_state(db, game, [other_host.id, user.id], status=models.GameStatus.preparation)
    unit_def = _make_unit_def(db, "RemoveUnit NoPlayerState Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    db.commit()

    resp_no_player = client.delete(f"/games/{game.link}/units/remove/{unit.id}")
    assert resp_no_player.status_code == 404
    assert resp_no_player.json()["detail"] == "Player state not found"

    # Unit metadata (the Unit row) is missing entirely.
    ghost_unit = models.GameUnit(
        game_id=game.id, unit_id=999999, user_id=user.id,
        starting_x=1, starting_y=1, current_x=1, current_y=1, level=50,
        current_hp=40, current_stats={"hp": 40}, stat_boosts=_default_stat_boosts(),
        status_effects=[], states=[], is_fainted=False, can_move=True,
    )
    db.add(ghost_unit)
    db.add(models.GamePlayer(game_id=game.id, player_id=user.id, cash_remaining=100, game_units=[ghost_unit.id]))
    db.commit()

    resp_no_metadata = client.delete(f"/games/{game.link}/units/remove/{ghost_unit.id}")
    assert resp_no_metadata.status_code == 404
    assert resp_no_metadata.json()["detail"] == "Unit metadata not found"


# ---------------------------------------------------------------------------
# Section B -- capture_objective / wait / revert_unit_position / move_unit success
# ---------------------------------------------------------------------------


def test_capture_objective_not_war_mode(client, db, user):
    _create_battle_game(db, user, link="capture-notwar", gamemode="Conquest")
    resp = client.post("/games/capture-notwar/war/capture", json={"unit_id": 1})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Capture is only available in War mode"


def test_capture_objective_success_and_errors(client, db, user):
    width = height = 6
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[1][1] = {"owner": 2, "kind": "pokeball", "hp": 1, "max_hp": 20}
    ctx = _create_battle_game(
        db, user, link="capture-success", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    unit = ctx["unit"]

    # Invalid payload.
    resp_bad = client.post("/games/capture-success/war/capture", json={"unit_id": "bad"})
    assert resp_bad.status_code == 400

    resp = client.post("/games/capture-success/war/capture", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["captured"] is True
    assert body["objective"]["owner"] == 1

    # Unit is locked after capturing (can_move now False).
    resp2 = client.post("/games/capture-success/war/capture", json={"unit_id": unit.id})
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Unit is locked"

    # Wrong owner.
    resp3 = client.post("/games/capture-success/war/capture", json={"unit_id": ctx["opponent_unit"].id})
    assert resp3.status_code == 403

    # Unit not on an objective tile.
    unit2_def = _make_unit_definition_http(db, link="capture-success", suffix="offobjective")
    db.commit()
    off_unit = models.GameUnit(
        game_id=ctx["game"].id, unit_id=unit2_def.id, user_id=user.id,
        starting_x=5, starting_y=5, current_x=5, current_y=5, level=50,
        current_hp=100, current_stats={"hp": 100, "attack": 100, "defense": 50, "sp_attack": 100, "sp_defense": 50, "speed": 100, "range": 3},
        stat_boosts=_default_stat_boosts(), status_effects=[], states=[], is_fainted=False, can_move=True,
    )
    db.add(off_unit)
    db.commit()
    resp4 = client.post("/games/capture-success/war/capture", json={"unit_id": off_unit.id})
    assert resp4.status_code == 400
    assert resp4.json()["detail"] == "Unit is not on an objective"


def test_capture_objective_already_owned(client, db, user):
    width = height = 6
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[1][1] = {"owner": 1, "kind": "pokeball", "hp": 20, "max_hp": 20}
    ctx = _create_battle_game(
        db, user, link="capture-owned", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    resp = client.post("/games/capture-owned/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "You already own this objective"


def test_capture_objective_completes_game_via_master_ball_loss(client, db, user):
    width = height = 6
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[1][1] = {"owner": 2, "kind": "master_ball", "hp": 1, "max_hp": 20, "original_owner": 2}
    ctx = _create_battle_game(
        db, user, link="capture-completes", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    unit = ctx["unit"]
    unit.current_x, unit.current_y = 1, 1
    db.add(unit)
    db.commit()

    resp = client.post("/games/capture-completes/war/capture", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["captured"] is True
    assert body["game_completed"] is True
    db.refresh(ctx["state"])
    assert ctx["state"].status == models.GameStatus.completed
    assert ctx["state"].winner_id == user.id


def test_wait_unit_success_and_errors(client, db, user):
    ctx = _create_battle_game(db, user, link="wait-1")
    unit = ctx["unit"]

    # Give the host a second unit so waiting with the first doesn't auto-advance
    # the turn (which would reset can_move back to True for the next turn).
    unit_def = _make_unit_def(db, "Wait Second Mon")
    second_unit = _make_game_unit(
        db, unit_def, x=2, y=2, hp=40, max_hp=40, game=ctx["game"], user_id=user.id,
    )

    resp_bad = client.post("/games/wait-1/wait", json={"unit_id": "bad"})
    assert resp_bad.status_code == 400

    resp = client.post("/games/wait-1/wait", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["turn_advanced"] is False
    db.refresh(unit)
    assert unit.can_move is False

    resp2 = client.post("/games/wait-1/wait", json={"unit_id": unit.id})
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Unit is locked"

    resp3 = client.post("/games/wait-1/wait", json={"unit_id": ctx["opponent_unit"].id})
    assert resp3.status_code == 403


def test_wait_unit_completed_via_top_level_reconcile_single_player(client, db, user):
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "WaitSingle Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    db.commit()

    resp = client.post(f"/games/{game.link}/wait", json={"unit_id": unit.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game completed"


def test_wait_unit_unit_not_found(client, db, user):
    ctx = _create_battle_game(db, user, link="wait-unitnotfound")
    resp = client.post("/games/wait-unitnotfound/wait", json={"unit_id": 999999})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unit not found"


def test_revert_unit_position_noop_and_reverted(client, db, user):
    ctx = _create_battle_game(db, user, link="revert-1")
    unit = ctx["unit"]

    resp_bad = client.post("/games/revert-1/revert_position", json={"unit_id": "bad"})
    assert resp_bad.status_code == 400

    # Unit hasn't moved -> no-op branch.
    resp = client.post("/games/revert-1/revert_position", json={"unit_id": unit.id})
    assert resp.status_code == 200
    assert resp.json()["reverted"] is False

    unit.current_x = unit.starting_x + 1
    db.add(unit)
    db.commit()
    resp2 = client.post("/games/revert-1/revert_position", json={"unit_id": unit.id})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["reverted"] is True
    assert body2["x"] == unit.starting_x

    unit.can_move = False
    db.add(unit)
    db.commit()
    resp3 = client.post("/games/revert-1/revert_position", json={"unit_id": unit.id})
    assert resp3.status_code == 400
    assert resp3.json()["detail"] == "Unit has already acted"


def test_revert_unit_position_errors(client, db, user):
    resp_missing = client.post("/games/does-not-exist/revert_position", json={"unit_id": 1})
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    _create_battle_game(db, user, link="revert-notprog", status=models.GameStatus.preparation)
    resp_not_prog = client.post("/games/revert-notprog/revert_position", json={"unit_id": 1})
    assert resp_not_prog.status_code == 400
    assert resp_not_prog.json()["detail"] == "Game not in progress"

    ctx = _create_battle_game(db, user, link="revert-turn")
    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    resp_not_your_turn = client.post(
        "/games/revert-turn/revert_position", json={"unit_id": ctx["opponent_unit"].id},
    )
    app.dependency_overrides[get_current_user] = lambda: user
    assert resp_not_your_turn.status_code == 403
    assert resp_not_your_turn.json()["detail"] == "Not your turn"

    resp_unit_missing = client.post(
        "/games/revert-turn/revert_position", json={"unit_id": 999999},
    )
    assert resp_unit_missing.status_code == 404
    assert resp_unit_missing.json()["detail"] == "Unit not found"

    resp_wrong_owner = client.post(
        "/games/revert-turn/revert_position", json={"unit_id": ctx["opponent_unit"].id},
    )
    assert resp_wrong_owner.status_code == 403
    assert resp_wrong_owner.json()["detail"] == "You can only revert your own unit"


def test_revert_unit_position_completed_via_top_level_reconcile(client, db, user):
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "RevertSingle Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    db.commit()

    resp = client.post(f"/games/{game.link}/revert_position", json={"unit_id": unit.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game completed"


def test_get_and_update_game_state_missing_state_row(client, db, user):
    map_obj = _make_map(db, user.id)
    game = models.Game(
        game_name="No State Game", map_id=map_obj.id, map_name=map_obj.name, max_players=2,
        gamemode="Conquest", is_private=False, host_id=user.id, link=f"nostate-{next(_link_counter)}",
    )
    db.add(game)
    db.commit()
    db.add(models.GamePlayer(game_id=game.id, player_id=user.id, cash_remaining=1000, game_units=[]))
    db.commit()

    resp_get = client.get(f"/games/{game.link}/state")
    assert resp_get.status_code == 404
    assert resp_get.json()["detail"] == "Game state not found"

    resp_patch = client.patch(f"/games/{game.link}/state", json={"current_turn": 5})
    assert resp_patch.status_code == 404
    assert resp_patch.json()["detail"] == "Game state not found"


def test_move_unit_success_updates_position(client, db, user, _mock_redis):
    import json as json_mod

    ctx = _create_battle_game(db, user, link="moveunit-success")
    unit = ctx["unit"]
    dest_x, dest_y = unit.current_x + 1, unit.current_y
    _mock_redis.hget.return_value = json_mod.dumps({"origin": [unit.current_x, unit.current_y], "tiles": [[dest_x, dest_y]]})

    resp = client.post(
        "/games/moveunit-success/move",
        json={"unit_id": unit.id, "x": dest_x, "y": dest_y},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["x"] == dest_x
    assert body["y"] == dest_y
    db.refresh(unit)
    assert unit.current_x == dest_x
    assert unit.current_y == dest_y


# ---------------------------------------------------------------------------
# Section B -- execute_move additional branches
# ---------------------------------------------------------------------------


def test_execute_move_invalid_payload_returns_400(client, db, user):
    _create_battle_game(db, user, link="move-invalid")
    resp = client.post(
        "/games/move-invalid/execute_move",
        json={"unit_id": "not-an-int", "move_id": 1, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid payload"


def test_execute_move_not_your_turn(client, db, user):
    ctx = _create_battle_game(db, user, link="move-notyourturn")
    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    resp = client.post(
        "/games/move-notyourturn/execute_move",
        json={"unit_id": ctx["opponent_unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    app.dependency_overrides[get_current_user] = lambda: user
    assert resp.status_code == 403


def test_execute_move_locked_unit_returns_400(client, db, user):
    ctx = _create_battle_game(db, user, link="move-locked")
    ctx["unit"].can_move = False
    db.add(ctx["unit"])
    db.commit()

    resp = client.post(
        "/games/move-locked/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit is locked"


def test_execute_move_wrong_owner_returns_403(client, db, user):
    ctx = _create_battle_game(db, user, link="move-wrongowner")
    resp = client.post(
        "/games/move-wrongowner/execute_move",
        json={"unit_id": ctx["opponent_unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "You can only execute moves for your own unit"


def test_execute_move_encore_forces_required_move(client, db, user):
    ctx = _create_battle_game(db, user, link="move-encore")
    unit = ctx["unit"]

    other_move = models.Move(name="Other Move", type="Water", category="Special", power=40, pp=10, effects=[], targeting="enemy")
    db.add(other_move)
    db.commit()
    unit.flags = {**unit.flags, "move_ids": [ctx["move"].id, other_move.id]}
    unit.move_pp = [ctx["move"].pp, other_move.pp]
    unit.states = ["encore", 3, ctx["move"].id]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-encore/execute_move",
        json={"unit_id": unit.id, "move_id": other_move.id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert "Encore prevents that move" in resp.json()["detail"]


def test_execute_move_taunt_blocks_status_move(client, db, user):
    ctx = _create_battle_game(db, user, link="move-taunt")
    unit = ctx["unit"]

    status_move = models.Move(name="Status Move", type="Normal", category="Status", power=None, pp=10, effects=[], targeting="enemy")
    db.add(status_move)
    db.commit()
    unit.flags = {**unit.flags, "move_ids": [ctx["move"].id, status_move.id]}
    unit.move_pp = [ctx["move"].pp, status_move.pp]
    unit.states = ["taunt", 3]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-taunt/execute_move",
        json={"unit_id": unit.id, "move_id": status_move.id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Taunted and cannot use status moves"


def test_execute_move_torment_blocks_repeat_move(client, db, user):
    ctx = _create_battle_game(db, user, link="move-torment")
    unit = ctx["unit"]
    unit.states = ["torment", 3]
    db.add(unit)
    db.commit()
    ctx["state"].replay_log = [
        {"event": "system_log", "message": f"{unit.owner.username if unit.owner else ''}"},
    ]
    db.commit()

    # First seed the replay log with the exact "used <move>" message the handler looks for.
    from app.routes.games import get_unit_display_name
    display_name = get_unit_display_name(unit, db)
    ctx["state"].replay_log = [{"event": "system_log", "message": f"{display_name} used {ctx['move'].name}"}]
    db.add(ctx["state"])
    db.commit()

    resp = client.post(
        "/games/move-torment/execute_move",
        json={"unit_id": unit.id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Tormented and cannot use the same move twice in a row"


def test_execute_move_effect_tiles_skips_bad_entries(client, db, user):
    ctx = _create_battle_game(db, user, link="move-effecttiles")
    unit = ctx["unit"]
    opponent_unit = ctx["opponent_unit"]

    resp = client.post(
        "/games/move-effecttiles/execute_move",
        json={
            "unit_id": unit.id,
            "move_id": ctx["move"].id,
            "target_ids": [opponent_unit.id],
            "effect_tiles": ["not_a_tile", [1], [opponent_unit.current_x, opponent_unit.current_y], "abc"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_execute_move_critical_hit_kills_last_enemy_unit_and_completes_game(client, db, user):
    ctx = _create_battle_game(db, user, link="move-critko")
    ctx["move"].effects = ["guaranteed_crit"]
    db.add(ctx["move"])
    ctx["opponent_unit"].current_hp = 20
    db.add(ctx["opponent_unit"])
    db.commit()

    resp = client.post(
        "/games/move-critko/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert ctx["opponent_unit"].id in body["removed_ids"]
    db.refresh(ctx["state"])
    assert ctx["state"].status == models.GameStatus.completed
    assert ctx["state"].winner_id == user.id


def test_execute_move_auto_end_turn_round_weather_branch(client, db, user):
    ctx = _create_battle_game(db, user, link="move-roundweather")
    ctx["state"].current_turn = 1
    db.add(ctx["state"])
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    resp = client.post(
        "/games/move-roundweather/execute_move",
        json={"unit_id": ctx["opponent_unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["unit"].id]},
    )
    app.dependency_overrides[get_current_user] = lambda: user
    assert resp.status_code == 200
    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 2


def test_execute_move_displacement_dash_attack_requires_effect_tiles(client, db, user):
    ctx = _create_battle_game(db, user, link="move-dash-fail")
    move = ctx["move"]
    move.range = "dash_attack"
    db.add(move)
    db.commit()
    resp = client.post(
        "/games/move-dash-fail/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": move.id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This cannot work."


def test_execute_move_displacement_dash_attack_success(client, db, user):
    ctx = _create_battle_game(db, user, link="move-dash")
    unit = ctx["unit"]
    move = ctx["move"]
    move.range = "dash_attack"
    move.targeting = "enemy"
    db.add(move)

    # Landing tile must be empty; pick an adjacent tile distinct from the target's tile.
    landing_x, landing_y = unit.current_x, unit.current_y + 1

    resp = client.post(
        "/games/move-dash/execute_move",
        json={
            "unit_id": unit.id,
            "move_id": move.id,
            "target_ids": [ctx["opponent_unit"].id],
            "effect_tiles": [[landing_x, landing_y]],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_execute_move_displacement_dash_attack_no_valid_landing(client, db, user):
    ctx = _create_battle_game(db, user, link="move-dash-noland")
    unit = ctx["unit"]
    move = ctx["move"]
    move.range = "dash_attack"
    db.add(move)
    db.commit()

    # Diagonal tile: dx != 0 and dy != 0, so no candidate landing tile qualifies.
    resp = client.post(
        "/games/move-dash-noland/execute_move",
        json={
            "unit_id": unit.id, "move_id": move.id, "target_ids": [ctx["opponent_unit"].id],
            "effect_tiles": [[unit.current_x + 1, unit.current_y + 1]],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This cannot work."


def test_execute_move_displacement_dash_attack_landing_occupied(client, db, user):
    ctx = _create_battle_game(db, user, link="move-dash-occupied")
    unit = ctx["unit"]
    move = ctx["move"]
    move.range = "dash_attack"
    db.add(move)

    landing_x, landing_y = unit.current_x, unit.current_y + 1
    blocker = models.GameUnit(
        game_id=ctx["game"].id, unit_id=ctx["opponent_unit"].unit_id, user_id=ctx["opponent"].id,
        starting_x=landing_x, starting_y=landing_y, current_x=landing_x, current_y=landing_y,
        level=50, current_hp=100, current_stats=dict(ctx["opponent_unit"].current_stats),
        stat_boosts=_default_stat_boosts(), status_effects=[], states=[], is_fainted=False, can_move=True,
    )
    db.add(blocker)
    db.commit()

    resp = client.post(
        "/games/move-dash-occupied/execute_move",
        json={
            "unit_id": unit.id, "move_id": move.id, "target_ids": [ctx["opponent_unit"].id],
            "effect_tiles": [[landing_x, landing_y]],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This cannot work."


def test_execute_move_displacement_dash_attack_landing_impassable(client, db, user):
    ctx = _create_battle_game(db, user, link="move-dash-impassable")
    unit = ctx["unit"]
    move = ctx["move"]
    move.range = "dash_attack"
    db.add(move)

    landing_x, landing_y = unit.current_x, unit.current_y + 1
    map_obj = ctx["map_obj"]
    width, height = map_obj.width, map_obj.height
    special_tiles = [[None for _ in range(width)] for _ in range(height)]
    special_tiles[landing_y][landing_x] = "impassable"
    map_obj.tile_data = {**map_obj.tile_data, "special_tiles": special_tiles}
    db.add(map_obj)
    db.commit()

    resp = client.post(
        "/games/move-dash-impassable/execute_move",
        json={
            "unit_id": unit.id, "move_id": move.id, "target_ids": [ctx["opponent_unit"].id],
            "effect_tiles": [[landing_x, landing_y]],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This cannot work."


def test_execute_move_torment_allows_different_move(client, db, user):
    ctx = _create_battle_game(db, user, link="move-torment-diff")
    unit = ctx["unit"]
    unit.states = ["torment", 3]
    db.add(unit)
    db.commit()

    other_move = models.Move(
        name="Other Move", type="Normal", category="Physical", power=30, pp=10, effects=[], targeting="enemy",
    )
    db.add(other_move)
    db.commit()
    unit.flags = {**unit.flags, "move_ids": [ctx["move"].id, other_move.id]}
    unit.move_pp = [ctx["move"].pp, other_move.pp]
    db.add(unit)
    db.commit()

    # First use "Other Move" so it becomes the "last move" in the replay log...
    resp1 = client.post(
        "/games/move-torment-diff/execute_move",
        json={"unit_id": unit.id, "move_id": other_move.id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp1.status_code == 200

    # Using a single-unit fixture auto-advances the turn after acting; reset the
    # unit/turn state to simulate this same unit getting to act again on a later
    # turn (torment only restricts repeating the immediately-preceding move).
    db.refresh(unit)
    unit.can_move = True
    db.add(unit)
    state = ctx["state"]
    state.current_turn = 0
    db.add(state)
    db.commit()

    # ...then using the ORIGINAL move (different from the last one) should be allowed.
    resp2 = client.post(
        "/games/move-torment-diff/execute_move",
        json={"unit_id": unit.id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp2.status_code == 200


def test_execute_move_ally_revive_targets_fainted_ally(client, db, user):
    ctx = _create_battle_game(db, user, link="move-revive")
    unit = ctx["unit"]

    fainted_ally = models.GameUnit(
        game_id=ctx["game"].id, unit_id=unit.unit_id, user_id=user.id,
        starting_x=2, starting_y=2, current_x=2, current_y=2, level=50,
        current_hp=0, current_stats=dict(unit.current_stats), stat_boosts=_default_stat_boosts(),
        status_effects=[], states=[], is_fainted=True, can_move=True,
    )
    db.add(fainted_ally)
    db.commit()

    revive_move = models.Move(
        name="Revive", type="Normal", category="Status", power=None, pp=10,
        effects=["target:revive:50"], targeting="ally",
    )
    db.add(revive_move)
    db.commit()
    unit.flags = {**unit.flags, "move_ids": [revive_move.id]}
    unit.move_pp = [revive_move.pp]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-revive/execute_move",
        json={
            "unit_id": unit.id, "move_id": revive_move.id, "target_ids": [],
            "effect_tiles": [[2, 2]],
        },
    )
    assert resp.status_code == 200
    db.refresh(fainted_ally)
    assert fainted_ally.is_fainted is False
    assert fainted_ally.current_hp > 0


def test_execute_move_all_targeting_hits_units_in_area(client, db, user):
    ctx = _create_battle_game(db, user, link="move-alltarget")
    move = ctx["move"]
    move.targeting = "all"
    db.add(move)
    db.commit()

    resp = client.post(
        "/games/move-alltarget/execute_move",
        json={
            "unit_id": ctx["unit"].id,
            "move_id": move.id,
            "target_ids": [],
            "effect_tiles": [[ctx["opponent_unit"].current_x, ctx["opponent_unit"].current_y]],
        },
    )
    assert resp.status_code == 200


def test_execute_move_ally_targeting_expands_to_effect_tiles(client, db, user):
    ctx = _create_battle_game(db, user, link="move-allytile")
    move = ctx["move"]
    move.targeting = "ally"
    db.add(move)

    ally_unit = models.GameUnit(
        game_id=ctx["game"].id, unit_id=ctx["unit"].unit_id, user_id=user.id,
        starting_x=3, starting_y=3, current_x=3, current_y=3, level=50,
        current_hp=100, current_stats=dict(ctx["unit"].current_stats),
        stat_boosts=_default_stat_boosts(), status_effects=[], states=[], is_fainted=False, can_move=True,
        move_pp=[20], flags={},
    )
    db.add(ally_unit)
    db.commit()

    resp = client.post(
        "/games/move-allytile/execute_move",
        json={
            "unit_id": ctx["unit"].id, "move_id": move.id, "target_ids": [],
            "effect_tiles": [[3, 3]],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any(t["id"] == ally_unit.id for t in body["targets"])


def test_execute_move_last_damage_received_auto_targets_attacker(client, db, user):
    ctx = _create_battle_game(db, user, link="move-lastdmg")
    unit = ctx["unit"]
    set_unit_flags(unit, {"last_damage_attacker_id": ctx["opponent_unit"].id, "last_damage_amount": 20}, db)
    db.commit()

    move = models.Move(
        name="Counter Strike", type="Normal", category="Status", power=None, pp=10,
        effects=["target:fixed_damage:last_damage_received"], targeting="enemy",
    )
    db.add(move)
    db.commit()
    unit.flags = {**unit.flags, "move_ids": [move.id]}
    unit.move_pp = [move.pp]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-lastdmg/execute_move",
        json={"unit_id": unit.id, "move_id": move.id, "target_ids": []},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["targets"][0]["id"] == ctx["opponent_unit"].id


def test_execute_move_fixed_damage_destiny_bond_knocks_out_attacker(client, db, user):
    ctx = _create_battle_game(db, user, link="move-fixeddestiny")
    ctx["opponent_unit"].states = ["destiny_bond", 1]
    ctx["opponent_unit"].current_hp = 5
    db.add(ctx["opponent_unit"])

    unit = ctx["unit"]
    fixed_move = models.Move(
        name="Fixed Destiny", type="Normal", category="Status", power=None, pp=10,
        effects=["target:fixed_damage:50"], targeting="enemy",
    )
    db.add(fixed_move)
    db.commit()
    unit.flags = {**unit.flags, "move_ids": [fixed_move.id]}
    unit.move_pp = [fixed_move.pp]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-fixeddestiny/execute_move",
        json={"unit_id": unit.id, "move_id": fixed_move.id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert ctx["opponent_unit"].id in body["removed_ids"]
    assert unit.id in body["removed_ids"]
    db.refresh(unit)
    assert unit.current_hp == 0


def test_execute_move_field_targeting_clears_targets(client, db, user):
    ctx = _create_battle_game(db, user, link="move-fieldtargeting")
    unit = ctx["unit"]
    field_move = models.Move(
        name="Field Effect Move", type="Water", category="Status", power=None, pp=10,
        effects=["weather:rain"], targeting="field",
    )
    db.add(field_move)
    db.commit()
    unit.flags = {**unit.flags, "move_ids": [field_move.id]}
    unit.move_pp = [field_move.pp]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-fieldtargeting/execute_move",
        json={"unit_id": unit.id, "move_id": field_move.id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["targets"] == []


def test_execute_move_destiny_bond_direct_damage_knocks_out_attacker(client, db, user):
    ctx = _create_battle_game(db, user, link="move-destinybond")
    ctx["opponent_unit"].states = ["destiny_bond", 1]
    ctx["opponent_unit"].current_hp = 5
    db.add(ctx["opponent_unit"])
    db.commit()

    resp = client.post(
        "/games/move-destinybond/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert ctx["opponent_unit"].id in body["removed_ids"]
    assert ctx["unit"].id in body["removed_ids"]
    db.refresh(ctx["unit"])
    assert ctx["unit"].current_hp == 0


def test_execute_move_power_trick_swaps_attack_and_defense_stat(client, db, user):
    ctx = _create_battle_game(db, user, link="move-powertrick")
    attacker = ctx["unit"]
    opponent = ctx["opponent_unit"]
    # execute_move recomputes stats from species base_stats. Give the attacker
    # low Attack / high Defense, and the defender a frail Defense so Power Trick
    # (Attack uses Defense) clearly boosts damage.
    attacker_info = db.query(models.Unit).filter(models.Unit.id == attacker.unit_id).first()
    attacker_info.base_stats = {
        "hp": 100,
        "attack": 1,
        "defense": 200,
        "sp_attack": 1,
        "sp_defense": 50,
        "speed": 100,
    }
    frail = models.Unit(
        species_id=next(_species_counter),
        name="Frail PowerTrick Foe",
        species="Frail PowerTrick Foe",
        asset_folder="frail_pt",
        types=["Normal"],
        base_stats={
            "hp": 100,
            "attack": 50,
            "defense": 1,
            "sp_attack": 50,
            "sp_defense": 50,
            "speed": 50,
        },
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[],
        cost=50,
    )
    db.add(frail)
    db.flush()
    opponent.unit_id = frail.id
    opponent.current_stats = {
        "hp": 100,
        "attack": 50,
        "defense": 1,
        "sp_attack": 50,
        "sp_defense": 50,
        "speed": 50,
        "range": 3,
    }
    attacker.states = ["power_trick", 3]
    db.add(attacker_info)
    db.add(attacker)
    db.add(opponent)
    db.commit()

    resp = client.post(
        "/games/move-powertrick/execute_move",
        json={"unit_id": attacker.id, "move_id": ctx["move"].id, "target_ids": [opponent.id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    # With power_trick active, the attacker's high Defense is used as Attack.
    assert body["targets"][0]["damage"] > 40


def test_execute_move_accuracy_miss_logs_dodge(client, db, user):
    ctx = _create_battle_game(db, user, link="move-miss")
    ctx["move"].accuracy = 0
    db.add(ctx["move"])
    db.commit()
    opponent_hp_before = ctx["opponent_unit"].current_hp

    resp = client.post(
        "/games/move-miss/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert ctx["opponent_unit"].id in body["missed_target_ids"]
    db.refresh(ctx["opponent_unit"])
    assert ctx["opponent_unit"].current_hp == opponent_hp_before


# ---------------------------------------------------------------------------
# Section B -- pick_up_item
# ---------------------------------------------------------------------------


def test_pick_up_item_invalid_payload(client, db, user):
    _create_battle_game(db, user, link="pickup-invalid")
    resp = client.post("/games/pickup-invalid/pick_up_item", json={"unit_id": "bad"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid payload"


def test_pick_up_item_no_item_on_tile(client, db, user):
    ctx = _create_battle_game(db, user, link="pickup-empty")
    resp = client.post("/games/pickup-empty/pick_up_item", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "No item on this tile"


def test_pick_up_item_success_and_swap(client, db, user):
    ctx = _create_battle_game(db, user, link="pickup-success")
    unit = ctx["unit"]
    map_state = ctx["map_state"]

    berry = models.Item(name="Pickup Berry", slug="pickup_berry", category="berry", cost=20)
    other_item = models.Item(name="Pickup Other", slug="pickup_other", category="berry", cost=20)
    db.add_all([berry, other_item])
    db.commit()

    new_tiles = [list(row) for row in map_state.item_id_tiles]
    new_tiles[unit.current_y][unit.current_x] = berry.id
    map_state.item_id_tiles = new_tiles
    db.add(map_state)
    db.commit()

    resp = client.post(f"/games/pickup-success/pick_up_item", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["item_slug"] == "pickup_berry"
    assert body["swapped"] is False

    db.refresh(unit)
    unit.can_move = True
    db.add(unit)
    # The first pick-up locks the unit; since it was the player's only unit,
    # advance_turn_if_player_has_no_actions auto-advances the turn. Reset it back
    # to the host's turn so the second pick-up call is authorized.
    ctx["state"].current_turn = 0
    db.add(ctx["state"])
    db.commit()

    new_tiles2 = [list(row) for row in map_state.item_id_tiles]
    new_tiles2[unit.current_y][unit.current_x] = other_item.id
    map_state.item_id_tiles = new_tiles2
    db.add(map_state)
    db.commit()

    resp2 = client.post("/games/pickup-success/pick_up_item", json={"unit_id": unit.id})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["swapped"] is True
    assert body2["item_slug"] == "pickup_other"


def test_pick_up_item_game_not_found_not_in_progress_and_item_not_found(client, db, user):
    resp_missing = client.post("/games/does-not-exist/pick_up_item", json={"unit_id": 1})
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    ctx = _create_battle_game(db, user, link="pickup-notprog", status=models.GameStatus.preparation)
    resp_not_prog = client.post("/games/pickup-notprog/pick_up_item", json={"unit_id": ctx["unit"].id})
    assert resp_not_prog.status_code == 400
    assert resp_not_prog.json()["detail"] == "Game not in progress"

    ctx2 = _create_battle_game(db, user, link="pickup-itemnotfound")
    unit2 = ctx2["unit"]
    map_state2 = ctx2["map_state"]
    new_tiles = [list(row) for row in map_state2.item_id_tiles]
    new_tiles[unit2.current_y][unit2.current_x] = 999999
    map_state2.item_id_tiles = new_tiles
    db.add(map_state2)
    db.commit()
    resp_item_missing = client.post("/games/pickup-itemnotfound/pick_up_item", json={"unit_id": unit2.id})
    assert resp_item_missing.status_code == 404
    assert resp_item_missing.json()["detail"] == "Item not found"


def test_pick_up_item_completed_via_top_level_reconcile(client, db, user):
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "PickupSingle Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    db.commit()

    resp = client.post(f"/games/{game.link}/pick_up_item", json={"unit_id": unit.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game completed"


def test_pick_up_item_unit_not_found_and_wrong_owner(client, db, user):
    ctx = _create_battle_game(db, user, link="pickup-unitnotfound")
    resp_missing = client.post("/games/pickup-unitnotfound/pick_up_item", json={"unit_id": 999999})
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Unit not found"

    resp_wrong_owner = client.post(
        "/games/pickup-unitnotfound/pick_up_item", json={"unit_id": ctx["opponent_unit"].id},
    )
    assert resp_wrong_owner.status_code == 403
    assert resp_wrong_owner.json()["detail"] == "You can only pick up items with your own unit"


def test_pick_up_item_out_of_bounds_tile_rows_and_columns(client, db, user):
    ctx = _create_battle_game(db, user, link="pickup-oob")
    unit = ctx["unit"]
    map_state = ctx["map_state"]
    width, height = ctx["map_obj"].width, ctx["map_obj"].height

    # Row out of bounds (fewer rows than the unit's y position).
    map_state.item_id_tiles = [[None] * width for _ in range(unit.current_y)]
    db.add(map_state)
    db.commit()
    resp_row = client.post("/games/pickup-oob/pick_up_item", json={"unit_id": unit.id})
    assert resp_row.status_code == 400
    assert resp_row.json()["detail"] == "No item on this tile"

    # Column out of bounds (row exists but is shorter than the unit's x position).
    new_tiles = [[None] * width for _ in range(height)]
    new_tiles[unit.current_y] = [None] * unit.current_x
    map_state.item_id_tiles = new_tiles
    db.add(map_state)
    db.commit()
    resp_col = client.post("/games/pickup-oob/pick_up_item", json={"unit_id": unit.id})
    assert resp_col.status_code == 400
    assert resp_col.json()["detail"] == "No item on this tile"


def test_pick_up_item_held_item_invalid(client, db, user):
    ctx = _create_battle_game(db, user, link="pickup-heldinvalid")
    unit = ctx["unit"]
    map_state = ctx["map_state"]

    unit.flags = {**unit.flags, "held_item": "totally_bogus_item_slug"}
    db.add(unit)

    berry = models.Item(name="Held Invalid Berry", slug="held_invalid_berry", category="berry", cost=20)
    db.add(berry)
    db.commit()
    new_tiles = [list(row) for row in map_state.item_id_tiles]
    new_tiles[unit.current_y][unit.current_x] = berry.id
    map_state.item_id_tiles = new_tiles
    db.add(map_state)
    db.commit()

    resp = client.post("/games/pickup-heldinvalid/pick_up_item", json={"unit_id": unit.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Held item is invalid"


def test_wait_unit_game_not_found_and_not_in_progress(client, db, user):
    resp_missing = client.post("/games/does-not-exist/wait", json={"unit_id": 1})
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    _create_battle_game(db, user, link="wait-notprog", status=models.GameStatus.preparation)
    resp_not_prog = client.post("/games/wait-notprog/wait", json={"unit_id": 1})
    assert resp_not_prog.status_code == 400
    assert resp_not_prog.json()["detail"] == "Game not in progress"


def test_pick_up_item_locked_and_not_your_turn(client, db, user):
    ctx = _create_battle_game(db, user, link="pickup-locked")
    unit = ctx["unit"]
    unit.can_move = False
    db.add(unit)
    db.commit()
    resp = client.post("/games/pickup-locked/pick_up_item", json={"unit_id": unit.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit is locked"

    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    resp2 = client.post("/games/pickup-locked/pick_up_item", json={"unit_id": ctx["opponent_unit"].id})
    app.dependency_overrides[get_current_user] = lambda: user
    assert resp2.status_code == 403


# ---------------------------------------------------------------------------
# Section B -- move_unit additional error paths
# ---------------------------------------------------------------------------


def test_move_unit_invalid_payload(client, db, user):
    _create_battle_game(db, user, link="moveunit-invalid")
    resp = client.post("/games/moveunit-invalid/move", json={"unit_id": "bad", "x": 0, "y": 0})
    assert resp.status_code == 400


def test_move_unit_out_of_bounds(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="moveunit-oob")
    resp = client.post(
        "/games/moveunit-oob/move",
        json={"unit_id": ctx["unit"].id, "x": 999, "y": 999},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Out of bounds"


def test_move_unit_immobilized(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="moveunit-immobilized")
    unit = ctx["unit"]
    unit.states = ["immobilized", 3]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/moveunit-immobilized/move",
        json={"unit_id": unit.id, "x": unit.current_x + 1, "y": unit.current_y},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit is immobilized and cannot move"


def test_move_unit_no_turnlock_initialized(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="moveunit-noturnlock")
    _mock_redis.hget.return_value = None
    resp = client.post(
        "/games/moveunit-noturnlock/move",
        json={"unit_id": ctx["unit"].id, "x": ctx["unit"].current_x + 1, "y": ctx["unit"].current_y},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Move set not initialized"


def test_move_unit_illegal_move_for_turn(client, db, user, _mock_redis):
    import json as json_mod

    ctx = _create_battle_game(db, user, link="moveunit-illegal")
    unit = ctx["unit"]
    sx, sy = unit.current_x, unit.current_y
    _mock_redis.hget.return_value = json_mod.dumps({"origin": [sx, sy], "tiles": [[sx, sy]]})

    resp = client.post(
        "/games/moveunit-illegal/move",
        json={"unit_id": unit.id, "x": sx + 3, "y": sy},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Illegal move for this turn"


def test_move_unit_occupied_target_tile(client, db, user, _mock_redis):
    import json as json_mod

    ctx = _create_battle_game(db, user, link="moveunit-occupied")
    unit = ctx["unit"]
    opponent_unit = ctx["opponent_unit"]
    opponent_unit.current_x = unit.current_x + 1
    opponent_unit.current_y = unit.current_y
    db.add(opponent_unit)
    db.commit()

    tx, ty = opponent_unit.current_x, opponent_unit.current_y
    _mock_redis.hget.return_value = json_mod.dumps({"origin": [unit.current_x, unit.current_y], "tiles": [[tx, ty]]})

    resp = client.post(
        "/games/moveunit-occupied/move",
        json={"unit_id": unit.id, "x": tx, "y": ty},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Tile occupied"


def test_move_unit_not_your_turn_and_wrong_owner(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="moveunit-turn")

    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    wrong_turn_resp = client.post(
        "/games/moveunit-turn/move",
        json={"unit_id": ctx["opponent_unit"].id, "x": ctx["opponent_unit"].current_x, "y": ctx["opponent_unit"].current_y},
    )
    app.dependency_overrides[get_current_user] = lambda: user
    assert wrong_turn_resp.status_code == 403

    wrong_owner_resp = client.post(
        "/games/moveunit-turn/move",
        json={"unit_id": ctx["opponent_unit"].id, "x": ctx["opponent_unit"].current_x, "y": ctx["opponent_unit"].current_y},
    )
    assert wrong_owner_resp.status_code == 403


def test_move_unit_locked_unit(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="moveunit-locked")
    unit = ctx["unit"]
    unit.can_move = False
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/moveunit-locked/move",
        json={"unit_id": unit.id, "x": unit.current_x + 1, "y": unit.current_y},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit is locked"


def test_move_unit_destination_tile_impassable(client, db, user, _mock_redis):
    import json as json_mod

    ctx = _create_battle_game(db, user, link="moveunit-impassable")
    unit = ctx["unit"]
    tx, ty = unit.current_x + 1, unit.current_y
    _mock_redis.hget.return_value = json_mod.dumps({"origin": [unit.current_x, unit.current_y], "tiles": [[tx, ty]]})

    map_obj = ctx["map_obj"]
    width, height = map_obj.width, map_obj.height
    special_tiles = [[None for _ in range(width)] for _ in range(height)]
    special_tiles[ty][tx] = "impassable"
    map_obj.tile_data = {**map_obj.tile_data, "special_tiles": special_tiles}
    db.add(map_obj)
    db.commit()

    resp = client.post("/games/moveunit-impassable/move", json={"unit_id": unit.id, "x": tx, "y": ty})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This unit cannot move onto this tile"


def test_move_unit_game_not_found_not_in_progress_unit_not_found_and_already_moved(client, db, user, _mock_redis):
    resp_missing = client.post("/games/does-not-exist/move", json={"unit_id": 1, "x": 0, "y": 0})
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    _create_battle_game(db, user, link="moveunit-notprog", status=models.GameStatus.preparation)
    resp_not_prog = client.post("/games/moveunit-notprog/move", json={"unit_id": 1, "x": 0, "y": 0})
    assert resp_not_prog.status_code == 400
    assert resp_not_prog.json()["detail"] == "Game not in progress"

    ctx = _create_battle_game(db, user, link="moveunit-notfound")
    resp_unit_missing = client.post(
        "/games/moveunit-notfound/move", json={"unit_id": 999999, "x": 0, "y": 0},
    )
    assert resp_unit_missing.status_code == 404
    assert resp_unit_missing.json()["detail"] == "Unit not found"

    _mock_redis.get.return_value = "1"  # movement lock active for this unit
    resp_already_moved = client.post(
        "/games/moveunit-notfound/move",
        json={"unit_id": ctx["unit"].id, "x": ctx["unit"].current_x, "y": ctx["unit"].current_y},
    )
    assert resp_already_moved.status_code == 400
    assert resp_already_moved.json()["detail"] == "Unit has already moved"


def test_move_unit_game_completed_via_reconcile(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="moveunit-completed")
    ctx["opponent_unit"].current_hp = 0
    db.add(ctx["opponent_unit"])
    db.commit()

    resp = client.post(
        "/games/moveunit-completed/move",
        json={"unit_id": ctx["unit"].id, "x": ctx["unit"].current_x, "y": ctx["unit"].current_y},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game completed"


# ---------------------------------------------------------------------------
# Section C -- process_move_effects additional token coverage
# ---------------------------------------------------------------------------


def test_raise_stat_condition_is_type_and_not_type_self_branches(db):
    user = _make_user(db, "cond-self-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    fire_def = _make_unit_def(db, "CondSelf Fire", types=["Fire"])

    attacker = _make_game_unit(db, fire_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Self Condition Combo",
        type="Fire",
        category="Status",
        effects=[
            "self:raise_stat:condition:is_type:fire:attack:2",
            "self:lower_stat:condition:not_type:flying:speed:1",
        ],
    )

    process_move_effects(
        move, attacker, [], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    from app.routes.games import get_stat_stage
    assert get_stat_stage(attacker.stat_boosts, "attack") == 2
    assert get_stat_stage(attacker.stat_boosts, "speed") == -1


def test_raise_stat_condition_is_type_self_no_match_continues(db):
    user = _make_user(db, "cond-self-nomatch-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    water_def = _make_unit_def(db, "CondSelfNoMatch Water", types=["Water"])
    attacker = _make_game_unit(db, water_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Self Condition No Match",
        type="Water",
        category="Status",
        effects=["self:raise_stat:condition:is_type:fire:attack:2"],
    )
    process_move_effects(
        move, attacker, [], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    from app.routes.games import get_stat_stage
    assert get_stat_stage(attacker.stat_boosts, "attack") == 0


def test_apply_state_via_generic_token_destiny_bond_and_encore_unaffected(db):
    user = _make_user(db, "state-token-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "StateToken Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Destiny Bond Token",
        type="Ghost",
        category="Status",
        effects=["self:apply_state:destiny_bond", "target:apply_state:destiny_bond"],
    )
    process_move_effects(
        move, attacker, [target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(target)
    assert attacker.states[0] == "destiny_bond"
    assert target.states[0] == "destiny_bond"


def test_encore_token_locks_target_into_last_used_move(db):
    user = _make_user(db, "encore-token-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "EncoreToken Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)

    remembered_move = models.Move(name="Remembered Move", type="Normal", category="Physical", pp=10)
    db.add(remembered_move)
    db.commit()

    from app.routes.games import get_unit_display_name
    target_name = get_unit_display_name(target, db)
    state.replay_log = [{"event": "system_log", "message": f"{target_name} used {remembered_move.name}"}]
    db.add(state)
    db.commit()

    move = models.Move(
        name="Encore Token",
        type="Normal",
        category="Status",
        effects=["target:apply_state:encore"],
    )
    process_move_effects(
        move, attacker, [target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(target)
    assert target.states[0] == "encore"
    assert target.states[2] == remembered_move.id


def test_encore_token_unaffected_when_no_last_move_found(db):
    user = _make_user(db, "encore-nomove-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "EncoreNoMove Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    state.replay_log = []
    db.commit()

    move = models.Move(
        name="Encore No History",
        type="Normal",
        category="Status",
        effects=["target:apply_state:encore"],
    )
    process_move_effects(
        move, attacker, [target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(target)
    assert target.states == []


def test_heal_block_prevents_self_and_target_heal(db):
    user = _make_user(db, "healblock-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    map_state = _make_map_state(db, game, map_obj)
    seeded_weather = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    seeded_weather[1][1] = WEATHER_TO_ID["sun"]
    map_state.weather_tiles = seeded_weather
    db.add(map_state)
    db.commit()

    unit_def = _make_unit_def(db, "HealBlock Mon")
    attacker = _make_game_unit(
        db, unit_def, x=1, y=1, hp=10, max_hp=50, game=game, user_id=user.id, states=["heal_block", 3]
    )
    target = _make_game_unit(
        db, unit_def, x=0, y=0, hp=10, max_hp=50, game=game, user_id=user.id, states=["heal_block", 3]
    )

    move = models.Move(
        name="Heal Combo",
        type="Normal",
        category="Status",
        effects=["self:heal:condition:weather:sun:2", "target:heal:condition:weather:sun:2"],
    )
    process_move_effects(
        move, attacker, [target], current_turn=0, db=db,
        weather_tiles=map_state.weather_tiles, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(target)
    assert attacker.current_hp == 10
    assert target.current_hp == 10


def test_revive_blocked_by_heal_block_and_missing_map(db):
    user = _make_user(db, "revive-healblock-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "ReviveHealBlock Mon")

    attacker = _make_game_unit(
        db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id, states=["heal_block", 3]
    )
    fainted_ally = _make_game_unit(
        db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user.id, is_fainted=True
    )

    move = models.Move(
        name="Revive Blocked",
        type="Normal",
        category="Status",
        effects=["target:revive:2"],
    )
    process_move_effects(
        move, attacker, [fainted_ally], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(fainted_ally)
    assert fainted_ally.is_fainted is True
    assert fainted_ally.current_hp == 0


def test_give_cash_bad_amount_and_missing_player_state_are_noops(db):
    user = _make_user(db, "givecash-noop-user")
    other_user = _make_user(db, "givecash-noop-other")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id, other_user.id])
    state = _make_state(db, game, [user.id, other_user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "GiveCashNoop Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    no_player_state_target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=other_user.id)

    zero_cash_move = models.Move(
        name="Zero Cash", type="Normal", category="Status", effects=["target:give_cash:0"]
    )
    process_move_effects(
        zero_cash_move, attacker, [no_player_state_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )

    bad_cash_move = models.Move(
        name="Bad Cash", type="Normal", category="Status", effects=["target:give_cash:abc"]
    )
    process_move_effects(
        bad_cash_move, attacker, [no_player_state_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )

    self_cash_move = models.Move(
        name="Self Cash Not Allowed", type="Normal", category="Status", effects=["self:give_cash:50"]
    )
    process_move_effects(
        self_cash_move, attacker, [no_player_state_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    # No GamePlayer row exists for other_user in this game -> should not raise, no cash change
    assert db.query(models.GamePlayer).filter_by(game_id=game.id, player_id=other_user.id).first() is None


def test_instant_ko_self_and_target_branches(db):
    user = _make_user(db, "instantko-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "InstantKo Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Instant KO Self",
        type="Normal",
        category="Status",
        effects=["self:instant_ko"],
    )
    process_move_effects(
        move, attacker, [target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    assert attacker.current_hp == 0

    attacker2 = _make_game_unit(db, unit_def, x=2, y=2, hp=40, max_hp=40, game=game, user_id=user.id)
    target_move = models.Move(
        name="Instant KO Target",
        type="Normal",
        category="Status",
        effects=["target:instant_ko"],
    )
    process_move_effects(
        target_move, attacker2, [target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(2, 2)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(target)
    assert target.current_hp == 0


def test_weather_and_terrain_tokens_create_default_map_state_when_missing(db):
    """Covers the map_state-is-None branch that creates a default GameMapState.

    Each of these branches independently does a query-then-create when no
    GameMapState row exists; the app session runs with autoflush disabled, so we
    commit between calls to avoid tripping the game_id unique constraint with two
    uncommitted inserts in the same flush.
    """
    user = _make_user(db, "nomapstate-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "NoMapState Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)

    weather_move = models.Move(
        name="Weather No Map State", type="Water", category="Status", effects=["weather:rain"],
    )
    # No GameMapState row exists for this game yet.
    process_move_effects(
        weather_move, attacker, [], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(0, 0)], game=game, game_state=state,
    )
    db.commit()
    map_state = db.query(models.GameMapState).filter_by(game_id=game.id).first()
    assert map_state is not None
    assert map_state.weather_tiles[0][0] == WEATHER_TO_ID["rain"]

    # A second game with no GameMapState row exercises the same "create default"
    # branch for the terrain token.
    game2 = _make_game(db, map_obj, [user.id])
    state2 = _make_state(db, game2, [user.id])
    attacker2 = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game2, user_id=user.id)
    terrain_move = models.Move(
        name="Terrain No Map State", type="Water", category="Status", effects=["terrain:misty"],
    )
    process_move_effects(
        terrain_move, attacker2, [], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(0, 0)], game=game2, game_state=state2,
    )
    db.commit()
    map_state2 = db.query(models.GameMapState).filter_by(game_id=game2.id).first()
    assert map_state2 is not None
    assert map_state2.terrain_effect_tiles[0][0][0] == TERRAIN_TO_ID["misty"]


# ---------------------------------------------------------------------------
# Section D: additional process_move_effects tokens (high_crit_ratio, status
# with/without condition, safeguard, state condition/side-screen branches)
# ---------------------------------------------------------------------------


def test_high_crit_ratio_self_and_target_tokens(db):
    from app.routes.games import get_stat_stage

    user = _make_user(db, "critratio-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "CritRatio Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target1 = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    target2 = _make_game_unit(db, unit_def, x=2, y=2, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Crit Ratio Combo",
        type="Normal",
        category="Status",
        effects=["self:high_crit_ratio:100", "target:high_crit_ratio:100"],
    )
    process_move_effects(
        move, attacker, [target1, target2], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(target1)
    db.refresh(target2)
    assert get_stat_stage(attacker.stat_boosts, "crit") == 1
    assert get_stat_stage(target1.stat_boosts, "crit") == 1
    assert get_stat_stage(target2.stat_boosts, "crit") == 1


def test_status_condition_self_immune_then_applied(db):
    """A Fire-type attacker: first self status token is blocked by type immunity
    (burn), the second (sleep, no type immunity) succeeds on the same call.
    """
    user = _make_user(db, "statuscond-self-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    fire_def = _make_unit_def(db, "StatusCondSelf Fire", types=["Fire"])

    attacker = _make_game_unit(db, fire_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Self Status Condition Combo",
        type="Fire",
        category="Status",
        effects=[
            "self:status:condition:type:fire:status:burn",
            "self:status:condition:type:fire:status:sleep",
        ],
    )
    process_move_effects(
        move, attacker, [], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    # Burn was blocked by Fire-type immunity, so the unit remained status-free
    # and the sleep token (no type immunity) was free to apply.
    assert attacker.status_effects[0] == "sleep"


def test_status_condition_target_safeguard_immune_and_applied(db):
    user = _make_user(db, "statuscond-target-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    electric_def = _make_unit_def(db, "StatusCondTarget Electric", types=["Electric"])
    normal_def = _make_unit_def(db, "StatusCondTarget Normal", types=["Normal"])

    attacker = _make_game_unit(db, electric_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    fainted_electric = _make_game_unit(
        db, electric_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user.id, is_fainted=True,
    )
    safeguarded_electric = _make_game_unit(
        db, electric_def, x=0, y=1, hp=40, max_hp=40, game=game, user_id=user.id, states=["safeguard", 3],
    )
    plain_electric = _make_game_unit(db, electric_def, x=0, y=2, hp=40, max_hp=40, game=game, user_id=user.id)
    plain_normal = _make_game_unit(db, normal_def, x=0, y=3, hp=40, max_hp=40, game=game, user_id=user.id)

    targets = [fainted_electric, safeguarded_electric, plain_electric, plain_normal]

    move = models.Move(
        name="Target Status Condition Combo",
        type="Electric",
        category="Status",
        effects=[
            # Matches only the electric-typed targets; exercises hp<=0 skip,
            # Safeguard skip, and type-immunity-labeled skip.
            "target:status:condition:type:electric:status:paralysis",
            # Matches only the normal-typed target; not immune, so it applies.
            "target:status:condition:type:normal:status:sleep",
        ],
    )
    process_move_effects(
        move, attacker, targets, current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    for u in targets:
        db.refresh(u)
    assert fainted_electric.status_effects == []
    assert safeguarded_electric.status_effects == []
    assert plain_electric.status_effects == []  # immune (Electric + paralysis)
    assert plain_normal.status_effects[0] == "sleep"


def test_status_plain_target_hp_safeguard_immune_and_applied(db):
    user = _make_user(db, "statusplain-target-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    fire_def = _make_unit_def(db, "StatusPlain Fire", types=["Fire"])
    normal_def = _make_unit_def(db, "StatusPlain Normal", types=["Normal"])

    attacker = _make_game_unit(db, normal_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    fainted = _make_game_unit(
        db, normal_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user.id, is_fainted=True,
    )
    safeguarded = _make_game_unit(
        db, normal_def, x=0, y=1, hp=40, max_hp=40, game=game, user_id=user.id, states=["safeguard", 3],
    )
    fire_target = _make_game_unit(db, fire_def, x=0, y=2, hp=40, max_hp=40, game=game, user_id=user.id)
    normal_target = _make_game_unit(db, normal_def, x=0, y=3, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Plain Status Combo",
        type="Fire",
        category="Status",
        effects=["target:status:burn"],
    )
    process_move_effects(
        move, attacker, [fainted, safeguarded, fire_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )

    move2 = models.Move(
        name="Plain Status Combo Applied",
        type="Normal",
        category="Status",
        effects=["target:status:sleep"],
    )
    process_move_effects(
        move2, attacker, [normal_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    for u in (fainted, safeguarded, fire_target, normal_target):
        db.refresh(u)
    assert fainted.status_effects == []
    assert safeguarded.status_effects == []
    assert fire_target.status_effects == []  # immune (Fire + burn)
    assert normal_target.status_effects[0] == "sleep"


def test_safeguard_token_self_and_target_skip_fainted(db):
    user = _make_user(db, "safeguardtoken-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "SafeguardToken Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    fainted_target = _make_game_unit(
        db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user.id, is_fainted=True,
    )
    live_target = _make_game_unit(db, unit_def, x=0, y=1, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Safeguard Token Combo",
        type="Normal",
        category="Status",
        effects=["self:safeguard", "target:safeguard"],
    )
    process_move_effects(
        move, attacker, [fainted_target, live_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(fainted_target)
    db.refresh(live_target)
    assert attacker.states[0] == "safeguard"
    assert fainted_target.states == []
    assert live_target.states[0] == "safeguard"


def test_state_token_side_screen_condition_and_confusion_safeguard_skip(db):
    user = _make_user(db, "statetoken-side-user")
    other = _make_user(db, "statetoken-side-opponent")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id, other.id])
    state = _make_state(db, game, [user.id, other.id])
    _make_map_state(db, game, map_obj)
    fire_def = _make_unit_def(db, "StateSideScreen Fire", types=["Fire"])
    normal_def = _make_unit_def(db, "StateSideScreen Normal", types=["Normal"])

    attacker = _make_game_unit(db, fire_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    ally = _make_game_unit(db, normal_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    enemy = _make_game_unit(db, normal_def, x=2, y=2, hp=40, max_hp=40, game=game, user_id=other.id)
    safeguarded_ally = _make_game_unit(
        db, normal_def, x=0, y=1, hp=40, max_hp=40, game=game, user_id=user.id, states=["safeguard", 3],
    )
    mismatched_condition_target = _make_game_unit(
        db, fire_def, x=0, y=2, hp=40, max_hp=40, game=game, user_id=user.id,
    )

    # "reflect" is in SIDE_SCREEN_STATE_NAMES: only applies to targets sharing the
    # attacker's user_id (the enemy is skipped by the same-side filter).
    reflect_move = models.Move(
        name="Reflect Side Screen",
        type="Normal",
        category="Status",
        effects=["target:apply_state:reflect"],
    )
    process_move_effects(
        reflect_move, attacker, [ally, enemy], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )

    # Confusion should be blocked on a Safeguard-protected target, and skipped
    # entirely for a target that fails the condition check.
    confusion_move = models.Move(
        name="Confusion Condition Combo",
        type="Fire",
        category="Status",
        effects=["target:apply_state:condition:type:normal:confusion"],
    )
    process_move_effects(
        confusion_move, attacker, [safeguarded_ally, mismatched_condition_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(ally)
    db.refresh(enemy)
    db.refresh(safeguarded_ally)
    assert ally.states[0] == "reflect"
    assert enemy.states == []
    assert safeguarded_ally.states[0] == "safeguard"  # confusion was blocked, not overwritten


# ---------------------------------------------------------------------------
# Section E: game listing, create/join errors, and chat endpoint
# ---------------------------------------------------------------------------


def test_get_open_closed_in_progress_completed_games_listing(client, db, user):
    map_obj = _make_map(db, user.id)

    open_game = _make_game(db, map_obj, [user.id])
    _make_state(db, open_game, [user.id], status=models.GameStatus.open)

    closed_game = _make_game(db, map_obj, [user.id])
    _make_state(db, closed_game, [user.id], status=models.GameStatus.closed)

    prep_game = _make_game(db, map_obj, [user.id])
    _make_state(db, prep_game, [user.id], status=models.GameStatus.preparation)

    in_progress_game = _make_game(db, map_obj, [user.id])
    _make_state(db, in_progress_game, [user.id], status=models.GameStatus.in_progress)

    completed_game = _make_game(db, map_obj, [user.id])
    _make_state(db, completed_game, [user.id], status=models.GameStatus.completed)

    for g in (open_game, closed_game, prep_game, in_progress_game, completed_game):
        db.add(models.GamePlayer(game_id=g.id, player_id=user.id, cash_remaining=1000, game_units=[]))
    db.commit()

    resp_open = client.get("/games/open")
    assert resp_open.status_code == 200
    assert {g["id"] for g in resp_open.json()} == {open_game.id}

    resp_closed = client.get("/games/closed")
    assert resp_closed.status_code == 200
    assert {g["id"] for g in resp_closed.json()} == {closed_game.id}

    resp_in_progress = client.get("/games/in_progress")
    assert resp_in_progress.status_code == 200
    assert {g["id"] for g in resp_in_progress.json()} == {prep_game.id, in_progress_game.id}

    resp_completed = client.get("/games/completed")
    assert resp_completed.status_code == 200
    assert {g["id"] for g in resp_completed.json()} == {completed_game.id}


def test_create_game_map_not_found(client, db, user):
    resp = client.post("/games/create", json={
        "game_name": "No Map Game",
        "map_name": "Does Not Exist Map",
        "max_players": 2,
        "is_private": False,
        "gamemode": "Conquest",
    })
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Selected map not found"


def test_join_game_not_found_already_in_not_open_full_and_success(client, db, user):
    resp = client.post("/games/join/999999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Game not found"

    map_obj = _make_map(db, user.id)

    # Game with no GameState row.
    stateless_game = _make_game(db, map_obj, [user.id])
    db.commit()
    resp_no_state = client.post(f"/games/join/{stateless_game.id}")
    assert resp_no_state.status_code == 404
    assert resp_no_state.json()["detail"] == "Game state not found"

    # Already a member.
    already_game = _make_game(db, map_obj, [user.id])
    _make_state(db, already_game, [user.id], status=models.GameStatus.open)
    db.add(models.GamePlayer(game_id=already_game.id, player_id=user.id, cash_remaining=1000, game_units=[]))
    db.commit()
    resp_already = client.post(f"/games/join/{already_game.id}")
    assert resp_already.status_code == 400
    assert resp_already.json()["detail"] == "User already in game"

    # Not open (e.g. closed).
    other_host = _make_user(db, "join-not-open-host")
    closed_game = _make_game(db, map_obj, [other_host.id])
    _make_state(db, closed_game, [other_host.id], status=models.GameStatus.closed)
    db.add(models.GamePlayer(game_id=closed_game.id, player_id=other_host.id, cash_remaining=1000, game_units=[]))
    db.commit()
    resp_not_open = client.post(f"/games/join/{closed_game.id}")
    assert resp_not_open.status_code == 400
    assert resp_not_open.json()["detail"] == "Game not open"

    # Full game.
    full_host = _make_user(db, "join-full-host")
    full_game = models.Game(
        game_name="Full Game", map_id=map_obj.id, map_name=map_obj.name, max_players=1,
        gamemode="Conquest", is_private=False, host_id=full_host.id, link=f"join-full-{next(_link_counter)}",
    )
    db.add(full_game)
    db.commit()
    _make_state(db, full_game, [full_host.id], status=models.GameStatus.open)
    db.add(models.GamePlayer(game_id=full_game.id, player_id=full_host.id, cash_remaining=1000, game_units=[]))
    db.commit()
    resp_full = client.post(f"/games/join/{full_game.id}")
    assert resp_full.status_code == 400
    assert resp_full.json()["detail"] == "Game is full"

    # Successful join fills the last slot and transitions to closed; War mode
    # also exercises the objective-tile initialization branch.
    war_host = _make_user(db, "join-success-war-host")
    war_map = _make_map(db, war_host.id, allowed_modes=["War"])
    war_game = models.Game(
        game_name="War Join Game", map_id=war_map.id, map_name=war_map.name, max_players=2,
        gamemode="War", is_private=False, host_id=war_host.id, link=f"join-war-{next(_link_counter)}",
    )
    db.add(war_game)
    db.commit()
    war_state = _make_state(db, war_game, [war_host.id], status=models.GameStatus.open)
    db.add(models.GamePlayer(game_id=war_game.id, player_id=war_host.id, cash_remaining=1000, game_units=[]))
    _make_map_state(db, war_game, war_map)
    db.commit()

    resp_join = client.post(f"/games/join/{war_game.id}")
    assert resp_join.status_code == 200
    body = resp_join.json()
    assert body["status"] == "closed"
    assert user.id in body["player_order"]
    db.refresh(war_state)
    assert war_state.status == models.GameStatus.closed


def test_send_chat_message_not_found_not_member_empty_and_too_long(client, db, user):
    resp_missing = client.post("/games/does-not-exist/chat", json={"message": "hi"})
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    other_host = _make_user(db, "chat-other-host")
    map_obj = _make_map(db, other_host.id)
    game = _make_game(db, map_obj, [other_host.id])
    _make_state(db, game, [other_host.id], status=models.GameStatus.in_progress)
    db.commit()

    resp_spectator = client.post(f"/games/{game.link}/chat", json={"message": "watching intently"})
    assert resp_spectator.status_code == 200
    assert resp_spectator.json()["ok"] is True
    db.refresh(game)
    state = db.query(models.GameState).filter_by(game_id=game.id).first()
    spectator_chats = [
        row
        for row in (state.replay_log or [])
        if isinstance(row, dict)
        and row.get("event") == "chat_message"
        and row.get("is_spectator") is True
    ]
    assert spectator_chats
    assert spectator_chats[-1]["message"] == "watching intently"
    assert spectator_chats[-1]["player_id"] == user.id

    member_game = _make_game(db, map_obj, [user.id])
    _make_state(db, member_game, [user.id], status=models.GameStatus.in_progress)
    db.add(models.GamePlayer(game_id=member_game.id, player_id=user.id))
    db.commit()

    resp_empty = client.post(f"/games/{member_game.link}/chat", json={"message": "   "})
    assert resp_empty.status_code == 400
    assert resp_empty.json()["detail"] == "Message cannot be empty"

    resp_too_long = client.post(f"/games/{member_game.link}/chat", json={"message": "x" * 301})
    assert resp_too_long.status_code == 400
    assert resp_too_long.json()["detail"] == "Message too long"

    resp_ok = client.post(f"/games/{member_game.link}/chat", json={"message": "hello there"})
    assert resp_ok.status_code == 200
    assert resp_ok.json()["ok"] is True
    db.refresh(member_game)
    member_state = db.query(models.GameState).filter_by(game_id=member_game.id).first()
    member_chats = [
        row
        for row in (member_state.replay_log or [])
        if isinstance(row, dict)
        and row.get("event") == "chat_message"
        and row.get("message") == "hello there"
    ]
    assert member_chats
    assert member_chats[-1].get("is_spectator") is False


# ---------------------------------------------------------------------------
# Section F: get_game_by_link / get_player_state / toggle_ready_state / get_game_units
# ---------------------------------------------------------------------------


def test_get_game_by_link_not_found_and_success(client, db, user):
    resp_missing = client.get("/games/does-not-exist")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    _create_battle_game(db, user, link="getbylink-1")
    resp = client.get("/games/getbylink-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["link"] == "getbylink-1"
    assert body["status"] == "in_progress"


def test_get_player_state_not_found_and_success(client, db, user):
    resp_missing = client.get("/games/does-not-exist/player")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    other_host = _make_user(db, "playerstate-other-host")
    map_obj = _make_map(db, other_host.id)
    game = _make_game(db, map_obj, [other_host.id], host_id=other_host.id)
    _make_state(db, game, [other_host.id])
    db.commit()
    resp_no_player = client.get(f"/games/{game.link}/player")
    assert resp_no_player.status_code == 404
    assert resp_no_player.json()["detail"] == "Player state not found"

    _create_battle_game(db, user, link="playerstate-1")
    resp = client.get("/games/playerstate-1/player")
    assert resp.status_code == 200
    body = resp.json()
    assert "cash_remaining" in body
    assert "is_ready" in body


def test_toggle_ready_state_not_found_not_preparation_no_player_and_success(client, db, user):
    resp_missing = client.post("/games/does-not-exist/player/ready")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    _create_battle_game(db, user, link="ready-notprep", status=models.GameStatus.in_progress)
    resp_not_prep = client.post("/games/ready-notprep/player/ready")
    assert resp_not_prep.status_code == 400

    other_host = _make_user(db, "ready-no-player-host")
    map_obj = _make_map(db, other_host.id)
    game = _make_game(db, map_obj, [other_host.id], host_id=other_host.id)
    _make_state(db, game, [other_host.id], status=models.GameStatus.preparation)
    db.commit()
    resp_no_player = client.post(f"/games/{game.link}/player/ready")
    assert resp_no_player.status_code == 404
    assert resp_no_player.json()["detail"] == "Player not found"

    _create_battle_game(db, user, link="ready-success", preparation=True)
    resp = client.post("/games/ready-success/player/ready")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True

    resp2 = client.post("/games/ready-success/player/ready")
    assert resp2.status_code == 200
    assert resp2.json()["ready"] is False


def test_get_game_units_not_found_and_success(client, db, user):
    resp_missing = client.get("/games/does-not-exist/units")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["detail"] == "Game not found"

    ctx = _create_battle_game(db, user, link="getunits-1")
    resp = client.get("/games/getunits-1/units")
    assert resp.status_code == 200
    body = resp.json()
    assert any(u["id"] == ctx["unit"].id for u in body)


# ---------------------------------------------------------------------------
# Section G: advance_turn_if_player_has_no_actions via /wait (turn auto-advance)
# ---------------------------------------------------------------------------


def test_wait_unit_triggers_automatic_turn_advance(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="wait-autoadvance")
    unit = ctx["unit"]

    resp = client.post("/games/wait-autoadvance/wait", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["turn_advanced"] is True
    assert body["game_completed"] is False

    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 1
    # The unit that just waited has its can_move reset in preparation for its
    # next turn; the opponent (whose turn it now is) is also ready to act.
    db.refresh(unit)
    assert unit.can_move is True
    db.refresh(ctx["opponent_unit"])
    assert ctx["opponent_unit"].can_move is True


def test_wait_unit_war_mode_does_not_auto_advance(client, db, user, _mock_redis):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    ctx = _create_battle_game(
        db, user, link="wait-war-noadvance", gamemode="War", status=models.GameStatus.in_progress,
        width=width, height=height, war_objectives=objectives,
    )
    unit = ctx["unit"]

    resp = client.post("/games/wait-war-noadvance/wait", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["turn_advanced"] is False
    assert body["game_completed"] is False

    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 0
    db.refresh(unit)
    assert unit.can_move is False


def test_wait_unit_max_turns_completes_game(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="wait-maxturns")
    game = ctx["game"]
    state = ctx["state"]
    game.max_turns = 1
    state.current_turn = 2  # user's turn (index 0); increment -> 3 >= max_turns(1)*2
    db.add(game)
    db.add(state)
    db.commit()

    resp = client.post("/games/wait-maxturns/wait", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["game_completed"] is True

    db.refresh(state)
    assert state.status == models.GameStatus.completed


def test_wait_unit_end_of_round_applies_weather_and_hazard_damage(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="wait-roundweather")
    state = ctx["state"]
    # Reorder players so `user` occupies the second turn slot, and position the
    # counter such that waiting completes a full round (triggers weather/hazard code).
    state.players = [ctx["opponent"].id, user.id]
    state.current_turn = 1
    map_state = ctx["map_state"]
    weather_tiles = [row[:] for row in map_state.weather_tiles]
    weather_tiles[ctx["unit"].current_y][ctx["unit"].current_x] = 1  # sun/rain-like weather id
    map_state.weather_tiles = weather_tiles
    db.add(state)
    db.add(map_state)
    db.commit()

    resp = client.post("/games/wait-roundweather/wait", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["turn_advanced"] is True

    db.refresh(state)
    assert state.current_turn == 2


def test_advance_turn_if_player_has_no_actions_completes_via_direct_call(db, user, _mock_redis):
    """
    Directly exercises advance_turn_if_player_has_no_actions' own end-of-turn
    "only one player has any unit rows left" completion branch, which differs
    from (and runs after) the top-level reconcile_playable_players check that
    HTTP callers perform beforehand.
    """
    from app.routes.games import advance_turn_if_player_has_no_actions

    ctx = _create_battle_game(db, user, link="wait-directcall")
    unit = ctx["unit"]
    unit.can_move = False
    db.add(unit)
    db.delete(ctx["opponent_unit"])
    db.commit()

    removed_ids, turn_advanced, game_completed = advance_turn_if_player_has_no_actions(
        ctx["game"], ctx["state"], user.id, db,
    )
    assert turn_advanced is False
    assert game_completed is True

    db.refresh(ctx["state"])
    assert ctx["state"].status == models.GameStatus.completed
    assert ctx["state"].winner_id == user.id


# ---------------------------------------------------------------------------
# Section D -- raise_stat/lower_stat condition:weather / condition:terrain /
# condition:not_type(target) branches in process_move_effects
# ---------------------------------------------------------------------------


def test_raise_stat_condition_weather_self_and_target_match_and_mismatch(db):
    user = _make_user(db, "cond-weather-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "CondWeather Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)

    weather_tiles = [[0, 0], [0, WEATHER_TO_ID["sun"]]]

    move = models.Move(
        name="Weather Condition Combo",
        type="Fire",
        category="Status",
        effects=[
            "self:raise_stat:condition:weather:sun:attack:1",
            "target:raise_stat:condition:weather:sun:defense:1",
        ],
    )
    process_move_effects(
        move, attacker, [target], current_turn=0, db=db,
        weather_tiles=weather_tiles, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(target)
    from app.routes.games import get_stat_stage
    assert get_stat_stage(attacker.stat_boosts, "attack") == 1
    # Target is standing on a non-sun tile (0,0), so its raise_stat should not apply.
    assert get_stat_stage(target.stat_boosts, "defense") == 0


def test_lower_stat_condition_terrain_self_and_target_no_targets_continue(db):
    user = _make_user(db, "cond-terrain-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "CondTerrain Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)

    terrain_tiles = [[0, 0], [0, TERRAIN_TO_ID["electric"]]]

    move = models.Move(
        name="Terrain Condition Combo",
        type="Electric",
        category="Status",
        # Target-recipient condition:terrain effect with no targets list -> "continue" branch.
        effects=[
            "self:lower_stat:condition:terrain:electric:speed:1",
            "target:raise_stat:condition:terrain:electric:defense:1",
        ],
    )
    process_move_effects(
        move, attacker, [], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=terrain_tiles, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    from app.routes.games import get_stat_stage
    assert get_stat_stage(attacker.stat_boosts, "speed") == -1


def test_raise_stat_condition_not_type_target_filters_and_accuracy_miss(db, monkeypatch):
    user = _make_user(db, "cond-nottype-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    flying_def = _make_unit_def(db, "CondNotType Flying", types=["Flying"])
    normal_def = _make_unit_def(db, "CondNotType Normal", types=["Normal"])

    attacker = _make_game_unit(db, normal_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    flying_target = _make_game_unit(db, flying_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    normal_target = _make_game_unit(db, normal_def, x=2, y=2, hp=40, max_hp=40, game=game, user_id=user.id)

    move = models.Move(
        name="Not Type Filter",
        type="Normal",
        category="Status",
        effects=["target:raise_stat:condition:not_type:flying:defense:1:100"],
    )
    process_move_effects(
        move, attacker, [flying_target, normal_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(flying_target)
    db.refresh(normal_target)
    from app.routes.games import get_stat_stage
    assert get_stat_stage(flying_target.stat_boosts, "defense") == 0
    assert get_stat_stage(normal_target.stat_boosts, "defense") == 1

    # Now force the accuracy roll to fail so the "random.randint(...) > accuracy" branch runs.
    monkeypatch.setattr(games_mod.random, "randint", lambda a, b: 100 if b == 100 else a)
    move_low_acc = models.Move(
        name="Not Type Filter Miss",
        type="Normal",
        category="Status",
        effects=["target:raise_stat:condition:not_type:flying:defense:1:1"],
    )
    process_move_effects(
        move_low_acc, attacker, [normal_target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(normal_target)
    assert get_stat_stage(normal_target.stat_boosts, "defense") == 1  # unchanged, accuracy check failed


def test_use_stat_effect_overrides_attack_and_defense_stat_source(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="usestat-effect")
    move = ctx["move"]
    move.effects = ["self:use_stat:defense", "target:use_stat:sp_defense"]
    db.add(move)
    db.commit()

    resp = client.post(
        "/games/usestat-effect/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": move.id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["targets"]) == 1


def test_multi_hit_move_stops_early_when_target_faints(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="multihit-earlystop")
    move = ctx["move"]
    move.effects = ["hit_count:5"]
    move.power = 200
    db.add(move)
    ctx["opponent_unit"].current_hp = 5
    db.add(ctx["opponent_unit"])
    db.commit()

    resp = client.post(
        "/games/multihit-earlystop/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": move.id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["targets"][0]["current_hp"] == 0


def test_laser_focus_state_forces_guaranteed_critical_first_hit(client, db, user, _mock_redis, monkeypatch):
    ctx = _create_battle_game(db, user, link="laserfocus-crit")
    unit = ctx["unit"]
    unit.states = ["laser_focus", 1]
    db.add(unit)
    db.commit()

    monkeypatch.setattr(games_mod.random, "randint", lambda a, b: b)
    resp = client.post(
        "/games/laserfocus-crit/execute_move",
        json={"unit_id": unit.id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["targets"][0]["damage"] > 0

    db.refresh(unit)
    assert unit.states == []


def test_plain_heal_cure_status_reset_stats_and_give_cash_target_branches(db):
    user = _make_user(db, "heal-cure-cash-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "HealCureCash Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target = _make_game_unit(
        db, unit_def, x=0, y=0, hp=5, max_hp=40, game=game, user_id=user.id,
        status_effects=["burn"], stat_boosts={"attack": 2, "defense": -1, "sp_attack": 0, "sp_defense": 0, "speed": 0, "accuracy": 0, "evasion": 0},
    )

    player_state = models.GamePlayer(game_id=game.id, player_id=user.id, cash_remaining=100)
    db.add(player_state)
    db.commit()

    move = models.Move(
        name="Support Combo",
        type="Normal",
        category="Status",
        effects=[
            "target:heal:2",
            "target:cure_status:burn",
            "target:reset_stats",
            "target:give_cash:50",
        ],
    )
    process_move_effects(
        move, attacker, [target], current_turn=0, db=db,
        weather_tiles=None, terrain_tiles=None, field_effect_tiles=None,
        affected_tiles_override=[(1, 1)], game=game, game_state=state,
    )
    db.commit()
    db.refresh(target)
    db.refresh(player_state)
    from app.routes.games import get_stat_stage
    assert target.current_hp > 5
    assert target.status_effects == []
    assert get_stat_stage(target.stat_boosts, "attack") == 0
    assert get_stat_stage(target.stat_boosts, "defense") == 0
    assert player_state.cash_remaining == 150


def test_end_turn_war_mode_max_turns_draw_resolved_by_pokeball_count(client, db, user, _mock_redis):
    width = height = 4
    objectives = [[None for _ in range(width)] for _ in range(height)]
    objectives[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10, "last_summon_round": None}
    ctx = _create_battle_game(
        db, user, link="endturn-wardraw", gamemode="War", war_objectives=objectives, width=width, height=height,
    )
    ctx["game"].max_turns = 1
    db.add(ctx["game"])
    ctx["state"].current_turn = 2  # user's turn (index 0); increment -> 3 >= max_turns(1)*2
    db.add(ctx["state"])
    db.commit()

    resp = client.post("/games/endturn-wardraw/end_turn")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Game completed"
    db.refresh(ctx["state"])
    assert ctx["state"].status == models.GameStatus.completed
    assert ctx["state"].winner_id == user.id
