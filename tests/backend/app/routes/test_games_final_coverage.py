"""Final coverage push for app.routes.games.

Targets the remaining coverage gaps left after test_games_http_actions_coverage.py,
test_games_process_effects_coverage.py, and test_games_remaining_coverage.py, with a
focus on:

- The newly-fixed destiny_bond/laser_focus sibling branches and the newly-fixed
  Embargo held-item suppression check in process_move_effects (previously dead code).
- war objective restoration on faint via remove_fainted_units_from_play.
- Many scattered guard-clause / edge-case branches across process_move_effects,
  execute_move, place_unit, and misc helpers.
"""

import itertools
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.db.models as models
import app.routes.games as games_module
from app.main import app
from app.dependencies import get_db, get_current_user
from app.routes.games import (
    FIELD_EFFECT_TO_ID,
    FIELD_HAZARD_TO_ID,
    TERRAIN_TO_ID,
    WEATHER_TO_ID,
    apply_state_effect,
    default_stat_boosts,
    get_stat_stage,
    get_unit_ability_id,
    get_unit_display_name,
    get_unit_flags,
    process_move_effects,
    publish_turn_remaining_warning_if_needed,
    remove_fainted_units_from_play,
    resolve_held_item_name,
    resolve_item_record,
    set_unit_ability_id,
)
from tests.backend.app.routes.test_games_http_actions_coverage import _create_battle_game

_species_counter = itertools.count(940000)
_link_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Local fixtures / builders (mirrors test_games_process_effects_coverage.py)
# ---------------------------------------------------------------------------


def _make_user(db, username):
    user = models.User(username=username, email=f"{username}@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _make_unit_def(db, name, *, types=None, base_stats=None, ability_ids=None):
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


def _make_map(db, creator_id, *, width=3, height=3, special_tiles=None, gamemode="Conquest"):
    tile_data = {"movement_cost": [[1] * width for _ in range(height)]}
    if special_tiles is not None:
        tile_data["special_tiles"] = special_tiles
    map_obj = models.Map(
        name=f"Final Coverage Map {next(_link_counter)}",
        creator_id=creator_id,
        is_official=True,
        width=width,
        height=height,
        tileset_names=["grass"],
        tile_data=tile_data,
        allowed_modes=[gamemode],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.commit()
    return map_obj


def _make_game(db, map_obj, user_ids, *, gamemode="Conquest", max_turns=None, turn_seconds=120):
    game = models.Game(
        game_name=f"Final Coverage Game {next(_link_counter)}",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=max(2, len(user_ids)),
        gamemode=gamemode,
        is_private=False,
        host_id=user_ids[0],
        link=f"final-cov-link-{next(_link_counter)}",
        max_turns=max_turns,
        turn_seconds=turn_seconds,
    )
    db.add(game)
    db.commit()
    return game


def _make_state(db, game, user_ids, *, current_turn=0):
    state = models.GameState(
        game_id=game.id,
        current_turn=current_turn,
        status=models.GameStatus.in_progress,
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
def http_user(db):
    u = models.User(username="finalcov-user", email="finalcov@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def client(db, http_user):
    def override_get_db():
        yield db

    def override_user():
        return http_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _make_unit_definition(db, *, link, suffix, cost=100, types=None, ability_ids=None):
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
        ability_ids=ability_ids or [],
        cost=cost,
        portrait_credits=[],
        sprite_credits=[],
        weight=1.0,
        height=1.0,
    )
    db.add(unit_info)
    db.flush()
    return unit_info


# ---------------------------------------------------------------------------
# publish_turn_remaining_warning_if_needed: dedup-loop continue branches
# ---------------------------------------------------------------------------


def test_publish_turn_remaining_warning_dedup_continue_branches(db):
    from datetime import datetime, timedelta, timezone

    user = _make_user(db, "warn-dedup-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    game.turn_seconds = 300
    db.add(game)
    db.commit()

    now = datetime.now(timezone.utc)
    # warning_seconds will be 60 (turn_seconds=300 > 60), current_turn_index=0, player=user.id
    replay_log = [
        "not-a-dict",  # isinstance check -> continue
        {"event": "chat"},  # event != system_log -> continue
        {"event": "system_log", "warning_type": "other"},  # warning_type mismatch -> continue
        {
            "event": "system_log",
            "warning_type": "turn_remaining",
            "turn_index": "not-an-int",  # triggers _as_int except branch, then mismatch -> continue
        },
        {
            "event": "system_log",
            "warning_type": "turn_remaining",
            "turn_index": 0,
            "warning_seconds": 999,  # mismatch -> continue
        },
        {
            "event": "system_log",
            "warning_type": "turn_remaining",
            "turn_index": 0,
            "warning_seconds": 60,
            "player_id": user.id + 999,  # mismatch -> continue
        },
    ]
    state = models.GameState(
        game_id=game.id,
        current_turn=0,
        status=models.GameStatus.in_progress,
        players=[user.id],
        turn_deadline=now + timedelta(seconds=20),
        replay_log=replay_log,
    )

    assert publish_turn_remaining_warning_if_needed(game, state, db, now) is True

    # Now with a fully-matching existing entry, dedup should short-circuit to False.
    state2 = models.GameState(
        game_id=game.id,
        current_turn=0,
        status=models.GameStatus.in_progress,
        players=[user.id],
        turn_deadline=now + timedelta(seconds=20),
        replay_log=[
            {
                "event": "system_log",
                "warning_type": "turn_remaining",
                "turn_index": 0,
                "warning_seconds": 60,
                "player_id": user.id,
            }
        ],
    )
    assert publish_turn_remaining_warning_if_needed(game, state2, db, now) is False


# ---------------------------------------------------------------------------
# get_unit_display_name: unit relationship missing -> query fallback -> id fallback
# ---------------------------------------------------------------------------


def test_get_unit_display_name_fallback_paths(db):
    user = _make_user(db, "dispname-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "Displayname Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game, user_id=user.id)

    # unit.unit relationship works normally.
    name = get_unit_display_name(unit, db)
    assert unit_def.name in name

    # Force the relationship to appear absent so the code falls back to a fresh
    # Unit query by unit_id.
    db.expire(unit, ["unit"])
    object.__setattr__(unit, "__dict__", unit.__dict__)
    unit2 = models.GameUnit(
        game_id=game.id,
        user_id=user.id,
        unit_id=unit_def.id,
        level=50,
        starting_x=1,
        starting_y=1,
        current_x=1,
        current_y=1,
        current_hp=10,
        current_stats={"hp": 10},
        stat_boosts=default_stat_boosts(),
    )
    # Do NOT commit unit2 -- unit2.unit is None (no relationship loaded), but
    # unit_id is set so the fallback db.query(Unit) path should find it.
    name2 = get_unit_display_name(unit2, db)
    assert unit_def.name in name2

    # unit_id pointing at nothing -> final fallback "Player X's Unit <id>"
    unit3 = models.GameUnit(
        game_id=game.id,
        user_id=user.id,
        unit_id=999999,
        level=50,
        starting_x=2,
        starting_y=2,
        current_x=2,
        current_y=2,
        current_hp=10,
        current_stats={"hp": 10},
        stat_boosts=default_stat_boosts(),
    )
    db.add(unit3)
    db.commit()
    name3 = get_unit_display_name(unit3, db)
    assert "Unit" in name3


# ---------------------------------------------------------------------------
# get_unit_ability_id / set_unit_ability_id / resolve_held_item_name /
# resolve_item_record edge branches
# ---------------------------------------------------------------------------


def test_ability_id_and_item_ref_edge_branches(db):
    # get_unit_ability_id: ability_id present but not castable to int -> except -> fallback to unit_info
    unit_def = _make_unit_def(db, "Ability Fallback Mon", ability_ids=[42])
    unit = models.GameUnit(flags={"ability_id": "not-an-int"})
    unit.unit = unit_def
    assert get_unit_ability_id(unit) == 42

    # set_unit_ability_id(None) pops the key
    unit2 = models.GameUnit(flags={"ability_id": 7})
    set_unit_ability_id(unit2, None, db)
    assert "ability_id" not in get_unit_flags(unit2)

    # resolve_held_item_name / resolve_item_record: whitespace-only ref -> None
    assert resolve_held_item_name("   ", db) is None
    assert resolve_item_record("   ", db) is None
    assert resolve_held_item_name(None, db) is None
    assert resolve_item_record(None, db) is None


# ---------------------------------------------------------------------------
# process_move_effects: Embargo held-item suppression (fixed dead-code bug)
# ---------------------------------------------------------------------------


def test_process_move_effects_embargo_suppresses_held_item_effects(db):
    user = _make_user(db, "embargo-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Embargo Mon")

    attacker = _make_game_unit(
        db, unit_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id,
        flags={"held_item": "oran_berry"},
        states=["embargo", 3],
    )
    target = _make_game_unit(
        db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id,
        flags={"held_item": "leftovers"},
        states=["embargo", 3],
    )

    move = models.Move(
        name="Embargo Consume",
        type="Normal",
        category="Status",
        effects=["self:consume_berry:held_item", "target:remove_held_item:held_item"],
    )

    process_move_effects(
        move,
        attacker,
        [target],
        current_turn=0,
        db=db,
        game=game,
        game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(target)

    # Both items should be untouched because Embargo suppressed the effects.
    assert get_unit_flags(attacker).get("held_item") == "oran_berry"
    assert get_unit_flags(target).get("held_item") == "leftovers"

    # Sanity: without embargo, the same tokens do consume/remove the item.
    attacker.states = []
    target.states = []
    db.add(attacker)
    db.add(target)
    db.commit()
    process_move_effects(
        move,
        attacker,
        [target],
        current_turn=0,
        db=db,
        game=game,
        game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(target)
    assert get_unit_flags(attacker).get("held_item") is None
    assert get_unit_flags(target).get("held_item") is None


# ---------------------------------------------------------------------------
# process_move_effects: weather/terrain/field_hazard/clear/tailwind/gravity
# guard-clause edge branches (game_id not int, missing game, missing map,
# zero-size map).
# ---------------------------------------------------------------------------


_FIELD_TOKENS = [
    "weather:sun",
    "terrain:electric",
    "field_hazard:spikes",
    "field:clear_hazards",
    "field:clear_substitutes",
    "self:clear_hazards",
    "field:tailwind",
    "field:gravity",
    "target:field_hazard:spikes",
]


def _field_move(token):
    return models.Move(name=f"Field Edge {token}", type="Normal", category="Status", effects=[token])


def test_field_tokens_bad_game_id_and_missing_game(db):
    user = _make_user(db, "field-edge-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "Field Edge Mon")

    # game_id not an int (None) -> every handler should hit its "continue" guard.
    attacker_no_game = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=None, user_id=user.id)
    for token in _FIELD_TOKENS:
        process_move_effects(_field_move(token), attacker_no_game, [], current_turn=0, db=db)

    # game_id valid int, but no matching Game row exists.
    attacker_bad_game = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=None, user_id=user.id)
    attacker_bad_game.game_id = 9999999
    db.add(attacker_bad_game)
    db.commit()
    for token in _FIELD_TOKENS:
        process_move_effects(_field_move(token), attacker_bad_game, [], current_turn=0, db=db)

    # Unknown weather/terrain/hazard names -> continue at the "id is None" guard.
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game, user_id=user.id)
    process_move_effects(_field_move("weather:not_a_weather"), attacker, [], current_turn=0, db=db, game=game)
    process_move_effects(_field_move("terrain:not_a_terrain"), attacker, [], current_turn=0, db=db, game=game)
    process_move_effects(_field_move("field_hazard:not_a_hazard"), attacker, [], current_turn=0, db=db, game=game)
    process_move_effects(_field_move("target:field_hazard:not_a_hazard"), attacker, [], current_turn=0, db=db, game=game)


def test_field_tokens_missing_map_and_zero_size_map(db):
    user = _make_user(db, "field-edge-user2")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "Field Edge Mon2")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game, user_id=user.id)

    # No GameMapState row + game.map_id pointing at a deleted map -> map lookup fails -> continue.
    game.map_id = 999999
    db.add(game)
    db.commit()
    for token in ["weather:sun", "terrain:electric", "field_hazard:spikes", "field:gravity"]:
        process_move_effects(_field_move(token), attacker, [], current_turn=0, db=db, game=game)
    # field:clear_hazards / field:clear_substitutes / self:clear_hazards / target:field_hazard
    # with no GameMapState row present also hit their own "continue" branches.
    for token in ["field:clear_hazards", "field:clear_substitutes", "self:clear_hazards", "target:field_hazard:spikes"]:
        process_move_effects(_field_move(token), attacker, [], current_turn=0, db=db, game=game)

    # Zero-size map -> height/width <= 0 continue branches.
    zero_map = _make_map(db, user.id, width=0, height=0)
    game2 = _make_game(db, zero_map, [user.id])
    attacker2 = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game2, user_id=user.id)
    for token in [
        "weather:sun",
        "terrain:electric",
        "field_hazard:spikes",
        "field:clear_hazards",
        "field:clear_substitutes",
        "field:tailwind",
        "field:gravity",
        "target:field_hazard:spikes",
    ]:
        process_move_effects(_field_move(token), attacker2, [], current_turn=0, db=db, game=game2)


def test_field_tokens_map_state_exists_but_map_missing(db):
    """map_state row exists (not None) but its .map relationship AND the
    fallback db.query(Map) both fail to resolve -> the `if not map_obj: continue`
    branch that follows the else-clause of the map_state-is-None check."""
    user = _make_user(db, "field-edge-user3")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    unit_def = _make_unit_def(db, "Field Edge Mon3")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game, user_id=user.id)

    map_state = models.GameMapState(
        game_id=game.id,
        map_id=999999,
        weather_tiles=[[0]],
        hazard_tiles=[[[]]],
        room_effect_tiles=[[0]],
        terrain_effect_tiles=[[[0, 0]]],
        field_effect_tiles=[[0]],
        item_id_tiles=[[None]],
    )
    db.add(map_state)
    game.map_id = 999999
    db.add(game)
    db.commit()

    for token in ["weather:sun", "terrain:electric", "field_hazard:spikes", "field:gravity"]:
        process_move_effects(_field_move(token), attacker, [], current_turn=0, db=db, game=game)


def test_field_hazard_target_variant_and_weather_terrain_normalize_paths(db):
    user = _make_user(db, "field-normalize-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Normalize Mon")

    # weather_tiles / terrain_effect_tiles stored malformed but *correctly sized*
    # (matches height) with individual bad rows, to hit the per-row normalization
    # branches (not-a-list row / wrong-length row).
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=[[0, 0, 0], "not-a-list", [0, 0]],
        hazard_tiles=[[[] for _ in range(3)] for _ in range(3)],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[[0, 0], [0, 0], [0, 0]], "not-a-list", [[0, 0], [0, 0]]],
        field_effect_tiles=[[0] * 3 for _ in range(3)],
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(map_state)
    db.commit()

    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)

    process_move_effects(
        _field_move("weather:sun"),
        attacker,
        [],
        current_turn=0,
        db=db,
        affected_tiles_override=[(0, 0), (0, 0), (10, 10)],
        game=game,
        game_state=state,
    )
    process_move_effects(
        _field_move("terrain:electric"),
        attacker,
        [],
        current_turn=0,
        db=db,
        affected_tiles_override=[(0, 0), (0, 0), (10, 10)],
        game=game,
        game_state=state,
    )
    process_move_effects(
        models.Move(name="Target Hazard", type="Normal", category="Status", effects=["target:field_hazard:spikes"]),
        attacker,
        [target],
        current_turn=0,
        db=db,
        game=game,
        game_state=state,
    )
    db.commit()


def test_terrain_wrong_size_rebuild_and_no_override_branches(db):
    """Hits the 'replace whole terrain_effect_tiles array' branch (wrong size)
    and the no-affected_tiles_override branch (uses get_move_affected_tiles)."""
    user = _make_user(db, "terrain-rebuild-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Terrain Rebuild Mon")

    map_state = models.GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=[[0] * 3 for _ in range(3)],
        hazard_tiles=[[[] for _ in range(3)] for _ in range(3)],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[0, 0]],  # wrong size vs height=3
        field_effect_tiles=[[0] * 3 for _ in range(3)],
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(map_state)
    db.commit()

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)

    # No affected_tiles_override -> uses get_move_affected_tiles() default (attacker's own tile).
    process_move_effects(
        _field_move("terrain:electric"), attacker, [], current_turn=0, db=db, game=game, game_state=state,
    )
    db.commit()
    db.refresh(map_state)
    assert map_state.terrain_effect_tiles[1][1][0] == TERRAIN_TO_ID["electric"]


def test_weather_wrong_size_rebuild_branch(db):
    user = _make_user(db, "weather-rebuild-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Weather Rebuild Mon")

    map_state = models.GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=[[0, 0]],  # wrong size vs height=3
        hazard_tiles=[[[] for _ in range(3)] for _ in range(3)],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[[0, 0] for _ in range(3)] for _ in range(3)],
        field_effect_tiles=[[0] * 3 for _ in range(3)],
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(map_state)
    db.commit()

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)
    process_move_effects(_field_move("weather:sun"), attacker, [], current_turn=0, db=db, game=game, game_state=state)
    db.commit()
    db.refresh(map_state)
    assert map_state.weather_tiles[1][1] == WEATHER_TO_ID["sun"]


def test_field_hazard_override_bounds_and_no_override_branches(db):
    user = _make_user(db, "hazard-bounds-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Hazard Bounds Mon")
    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)

    # Out-of-bounds + duplicate tiles in the override list.
    process_move_effects(
        _field_move("field_hazard:spikes"),
        attacker,
        [],
        current_turn=0,
        db=db,
        affected_tiles_override=[(-1, -1), (1, 1), (1, 1), (99, 99)],
        game=game,
        game_state=state,
    )
    # No override -> get_move_affected_tiles() default branch.
    process_move_effects(
        _field_move("field_hazard:stealth_rock"), attacker, [], current_turn=0, db=db, game=game, game_state=state,
    )


def test_clear_hazards_and_clear_substitutes_edge_branches(db):
    user = _make_user(db, "clear-edge-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Clear Edge Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id)

    # map_state exists but its map_id points nowhere and .map relationship is None
    # -> map_obj lookup fails on both paths -> continue. game.map_id must also be
    # invalid so the fallback db.query(Map) inside the handler can't recover it.
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=999999,
        weather_tiles=[[0]],
        hazard_tiles=[[[]]],
        room_effect_tiles=[[0]],
        terrain_effect_tiles=[[[0, 0]]],
        field_effect_tiles=[[0]],
        item_id_tiles=[[None]],
    )
    db.add(map_state)
    game.map_id = 999999
    db.add(game)
    db.commit()
    process_move_effects(_field_move("field:clear_hazards"), attacker, [], current_turn=0, db=db, game=game, game_state=state)

    # Now give it a real (zero-size) map -> height/width <= 0 branch.
    zero_map = _make_map(db, user.id, width=0, height=0)
    map_state.map_id = zero_map.id
    db.add(map_state)
    game.map_id = zero_map.id
    db.add(game)
    db.commit()
    process_move_effects(_field_move("field:clear_hazards"), attacker, [], current_turn=0, db=db, game=game, game_state=state)
    process_move_effects(_field_move("field:clear_substitutes"), attacker, [], current_turn=0, db=db, game=game, game_state=state)

    # Now a real, valid-sized map with no override -> get_move_affected_tiles() branch.
    real_map = _make_map(db, user.id, width=3, height=3)
    game.map_id = real_map.id
    map_state.map_id = real_map.id
    db.add(game)
    db.add(map_state)
    db.commit()
    process_move_effects(_field_move("field:clear_hazards"), attacker, [], current_turn=0, db=db, game=game, game_state=state)
    process_move_effects(_field_move("field:clear_substitutes"), attacker, [], current_turn=0, db=db, game=game, game_state=state)


def test_gravity_and_target_field_hazard_edge_branches(db):
    user = _make_user(db, "gravity-edge-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Gravity Edge Mon")
    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=2, y=2, hp=50, max_hp=50, game=game, user_id=user.id)

    # field_effect_tiles wrong size -> rebuild branch, plus no-override default-tiles branch.
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=[[0] * 3 for _ in range(3)],
        hazard_tiles=[[[] for _ in range(3)] for _ in range(3)],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[[0, 0] for _ in range(3)] for _ in range(3)],
        field_effect_tiles=[[0]],  # wrong size vs height=3
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(map_state)
    db.commit()
    process_move_effects(_field_move("field:gravity"), attacker, [], current_turn=0, db=db, game=game, game_state=state)

    # target:field_hazard -- map_state present but map lookup fails -> continue.
    map_state.map_id = 999999
    db.add(map_state)
    game.map_id = 999999
    db.add(game)
    db.commit()
    process_move_effects(
        models.Move(name="Target Hazard Edge", type="Normal", category="Status", effects=["target:field_hazard:spikes"]),
        attacker, [target], current_turn=0, db=db, game=game, game_state=state,
    )

    # target:field_hazard -- zero-size map -> height/width <= 0 branch.
    zero_map = _make_map(db, user.id, width=0, height=0)
    map_state.map_id = zero_map.id
    db.add(map_state)
    game.map_id = zero_map.id
    db.add(game)
    db.commit()
    process_move_effects(
        models.Move(name="Target Hazard Edge2", type="Normal", category="Status", effects=["target:field_hazard:spikes"]),
        attacker, [target], current_turn=0, db=db, game=game, game_state=state,
    )


def test_break_screens_and_defog_query_exceptions(db):
    user = _make_user(db, "screens-except-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Screens Except Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id, states=["reflect", 5])

    original_query = db.query

    def raising_query(model, *a, **kw):
        if model is models.GameUnit:
            raise RuntimeError("boom")
        return original_query(model, *a, **kw)

    db.query = raising_query
    try:
        process_move_effects(
            models.Move(name="Break Screens", type="Normal", category="Status", effects=["break_screens"]),
            attacker, [target], current_turn=0, db=db, game=game, game_state=state,
        )
        process_move_effects(
            models.Move(name="Defog", type="Normal", category="Status", effects=["target:defog"]),
            attacker, [target], current_turn=0, db=db, game=game, game_state=state,
        )
    finally:
        db.query = original_query

    # Sanity: without the query exception, break_screens/defog actually clear the state.
    db.refresh(target)
    assert target.states == ["reflect", 5]  # untouched since side_units lookup raised both times
    process_move_effects(
        models.Move(name="Break Screens2", type="Normal", category="Status", effects=["break_screens"]),
        attacker, [target], current_turn=0, db=db, game=game, game_state=state,
    )
    db.commit()
    db.refresh(target)
    assert target.states == []


def test_embargo_is_item_suppressed_exception_branch(db, monkeypatch):
    user = _make_user(db, "embargo-except-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    unit_def = _make_unit_def(db, "Embargo Except Mon")
    attacker = _make_game_unit(
        db, unit_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id, flags={"held_item": "oran_berry"}
    )

    original_is_item_suppressed = games_module.is_item_suppressed
    call_count = {"n": 0}

    def raising_once(unit):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return original_is_item_suppressed(unit)

    monkeypatch.setattr(games_module, "is_item_suppressed", raising_once)
    # Exception inside the embargo try/except should be swallowed, and processing
    # should continue normally to actually consume the berry.
    process_move_effects(
        models.Move(name="Embargo Except", type="Normal", category="Status", effects=["self:consume_berry:held_item"]),
        attacker, [], current_turn=0, db=db, game=game, game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    assert get_unit_flags(attacker).get("held_item") is None


# ---------------------------------------------------------------------------
# process_move_effects: raise_stat / lower_stat -- weather/terrain/is_type/
# not_type/plain condition edge branches.
# ---------------------------------------------------------------------------


def _stat_setup(db, *, attacker_types=None, target_types=None):
    user = _make_user(db, f"stat-edge-user-{next(_link_counter)}")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    attacker_def = _make_unit_def(db, f"Stat Attacker {next(_link_counter)}", types=attacker_types or ["Normal"])
    target_def = _make_unit_def(db, f"Stat Target {next(_link_counter)}", types=target_types or ["Normal"])
    attacker = _make_game_unit(db, attacker_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id)
    target = _make_game_unit(db, target_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)
    return game, state, attacker, target


def _run(move_effects, attacker, targets, db, game, state, name="Edge Move"):
    process_move_effects(
        models.Move(name=name, type="Normal", category="Status", effects=move_effects),
        attacker,
        targets,
        current_turn=0,
        db=db,
        game=game,
        game_state=state,
    )


def test_raise_stat_weather_condition_edge_branches(db, monkeypatch):
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    game, state, attacker, target = _stat_setup(db)

    # Magnitude ValueError -> continue.
    _run(["self:raise_stat:condition:weather:*:attack:bad"], attacker, [], db, game, state)
    # Dedup: same (recipient, stat) applied twice in one move -> second hits dedup continue.
    _run(
        ["self:raise_stat:condition:weather:*:attack:2", "self:raise_stat:condition:weather:*:attack:2"],
        attacker, [], db, game, state,
    )
    # target recipient with no targets -> continue.
    _run(["target:raise_stat:condition:weather:*:attack:2"], attacker, [], db, game, state)
    # target recipient with targets -> success path (weather_id lookup for targets[0]).
    _run(["target:raise_stat:condition:weather:*:attack:2"], attacker, [target], db, game, state)
    # invalid recipient (neither self nor target) -> continue.
    _run(["ally:raise_stat:condition:weather:*:attack:2"], attacker, [], db, game, state)
    # accuracy ValueError -> pass (effect still applies with default accuracy).
    _run(["self:raise_stat:condition:weather:*:defense:1:bad"], attacker, [], db, game, state)
    # weather condition doesn't match -> continue.
    _run(["self:raise_stat:condition:weather:sun:speed:1"], attacker, [], db, game, state)


def test_raise_stat_terrain_condition_edge_branches(db, monkeypatch):
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    game, state, attacker, target = _stat_setup(db)

    # Note: terrain condition "none" matches terrain_id == 0, which is what
    # attackers/targets resolve to when no terrain_tiles grid is supplied.
    _run(["self:raise_stat:condition:terrain:none:attack:bad"], attacker, [], db, game, state)
    _run(
        ["self:raise_stat:condition:terrain:none:attack:2", "self:raise_stat:condition:terrain:none:attack:2"],
        attacker, [], db, game, state,
    )
    _run(["target:raise_stat:condition:terrain:none:attack:2"], attacker, [], db, game, state)
    # target recipient with targets -> success path (terrain_id lookup for targets[0]).
    _run(["target:raise_stat:condition:terrain:none:attack:2"], attacker, [target], db, game, state)
    _run(["ally:raise_stat:condition:terrain:none:attack:2"], attacker, [], db, game, state)
    _run(["self:raise_stat:condition:terrain:none:defense:1:bad"], attacker, [], db, game, state)
    # terrain condition doesn't match -> continue.
    _run(["self:raise_stat:condition:terrain:psychic:speed:1"], attacker, [], db, game, state)


def test_raise_stat_is_type_and_not_type_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db, attacker_types=["Fire"], target_types=["Normal"])

    monkeypatch.setattr("random.randint", lambda a, b: 1)
    # is_type: magnitude ValueError.
    _run(["target:raise_stat:condition:is_type:fire:attack:bad"], attacker, [target], db, game, state)
    # is_type: accuracy ValueError -> pass.
    _run(["self:raise_stat:condition:is_type:fire:attack:1:bad"], attacker, [], db, game, state)
    # is_type: target recipient with no targets -> continue.
    _run(["target:raise_stat:condition:is_type:fire:attack:1"], attacker, [], db, game, state)
    # is_type: target recipient but no target matches condition -> continue.
    _run(["target:raise_stat:condition:is_type:fire:attack:1"], attacker, [target], db, game, state)
    # is_type: invalid recipient -> continue.
    _run(["ally:raise_stat:condition:is_type:fire:attack:1"], attacker, [], db, game, state)
    # is_type: self condition fails (attacker not matching type) -> continue.
    _run(["self:raise_stat:condition:is_type:water:attack:1"], attacker, [], db, game, state)

    # is_type: accuracy miss -> continue.
    monkeypatch.setattr("random.randint", lambda a, b: 100)
    _run(["self:raise_stat:condition:is_type:fire:attack:1:0"], attacker, [], db, game, state)

    # not_type: magnitude ValueError.
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    _run(["target:lower_stat:condition:not_type:flying:speed:bad"], attacker, [target], db, game, state)
    # not_type: accuracy ValueError -> pass.
    _run(["self:lower_stat:condition:not_type:flying:speed:1:bad"], attacker, [], db, game, state)
    # not_type: self condition fails (attacker IS the excluded type).
    _run(["self:lower_stat:condition:not_type:fire:speed:1"], attacker, [], db, game, state)
    # not_type: target recipient no targets -> continue.
    _run(["target:lower_stat:condition:not_type:flying:speed:1"], attacker, [], db, game, state)
    # not_type: target recipient, all targets excluded (target IS flying) -> continue.
    flying_target = _make_game_unit(
        db, _make_unit_def(db, f"Flying Target {next(_link_counter)}", types=["Flying"]),
        x=2, y=2, hp=50, max_hp=50, game=game, user_id=target.user_id,
    )
    _run(["target:lower_stat:condition:not_type:flying:speed:1"], attacker, [flying_target], db, game, state)
    # not_type: invalid recipient -> continue.
    _run(["ally:lower_stat:condition:not_type:flying:speed:1"], attacker, [], db, game, state)
    # not_type: successful apply path (covers the recipient=="target" apply loop).
    _run(["target:lower_stat:condition:not_type:flying:speed:1"], attacker, [target], db, game, state)


def test_raise_stat_plain_edge_branches(db, monkeypatch):
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    game, state, attacker, target = _stat_setup(db)

    # len(parts) < 4 -> continue (missing stat name / magnitude entirely).
    _run(["self:raise_stat"], attacker, [], db, game, state)
    # magnitude ValueError -> continue.
    _run(["self:raise_stat:attack:bad"], attacker, [], db, game, state)
    # accuracy ValueError -> pass.
    _run(["self:raise_stat:attack:2:bad"], attacker, [], db, game, state)
    # target recipient successful apply (covers common apply-to-targets loop).
    _run(["target:raise_stat:attack:1"], attacker, [target], db, game, state)
    # accuracy miss -> continue.
    monkeypatch.setattr("random.randint", lambda a, b: 100)
    _run(["self:raise_stat:attack:1:0"], attacker, [], db, game, state)


# ---------------------------------------------------------------------------
# process_move_effects: high_crit_ratio edge branches
# ---------------------------------------------------------------------------


def test_high_crit_ratio_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)

    # accuracy ValueError -> pass, then hit path applies to self.
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    _run(["self:high_crit_ratio:bad"], attacker, [], db, game, state)
    # accuracy miss -> continue.
    monkeypatch.setattr("random.randint", lambda a, b: 100)
    _run(["self:high_crit_ratio:0"], attacker, [], db, game, state)
    # target recipient hit path.
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    _run(["target:high_crit_ratio"], attacker, [target], db, game, state)


# ---------------------------------------------------------------------------
# process_move_effects: status (conditioned + plain) edge branches
# ---------------------------------------------------------------------------


def test_status_conditioned_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db, attacker_types=["Poison"], target_types=["Poison"])

    monkeypatch.setattr("random.randint", lambda a, b: 1)
    # parts[5] != "status" -> continue.
    _run(["self:status:condition:type:poison:notstatus:poison"], attacker, [], db, game, state)
    # accuracy ValueError -> pass.
    _run(["self:status:condition:type:poison:status:poison:bad"], attacker, [], db, game, state)
    # accuracy miss -> continue.
    monkeypatch.setattr("random.randint", lambda a, b: 100)
    _run(["self:status:condition:type:poison:status:poison:0"], attacker, [], db, game, state)
    monkeypatch.setattr("random.randint", lambda a, b: 1)

    # self recipient, condition matches, immune by type -> "wasn't poisoned" branch.
    _run(["self:status:condition:type:poison:status:poison"], attacker, [], db, game, state)
    # target recipient, condition matches, immune by type -> "wasn't poisoned" branch.
    _run(["target:status:condition:type:poison:status:poison"], attacker, [target], db, game, state)
    # target recipient, target fainted -> skip (continue).
    fainted_target = _make_game_unit(
        db, _make_unit_def(db, f"Fainted Target {next(_link_counter)}"),
        x=2, y=2, hp=0, max_hp=50, game=game, user_id=target.user_id, is_fainted=True,
    )
    _run(["target:status:condition:type:normal:status:burn"], attacker, [fainted_target], db, game, state)
    # target recipient protected by Safeguard -> skip with log + continue.
    safe_target = _make_game_unit(
        db, _make_unit_def(db, f"Safe Target {next(_link_counter)}", types=["Normal"]),
        x=2, y=1, hp=50, max_hp=50, game=game, user_id=target.user_id, states=["safeguard", 3],
    )
    _run(["target:status:condition:type:normal:status:burn"], attacker, [safe_target], db, game, state)
    # target recipient, applies successfully (not immune, condition matches, no safeguard).
    normal_target = _make_game_unit(
        db, _make_unit_def(db, f"Normal Target {next(_link_counter)}", types=["Normal"]),
        x=2, y=0, hp=50, max_hp=50, game=game, user_id=target.user_id,
    )
    _run(["target:status:condition:type:normal:status:burn"], attacker, [normal_target], db, game, state)

    # Force the "wasn't affected" (non-poisoned/burned/etc label) branches via a
    # monkeypatched label lookup, since the real STATUS_LOG_LABELS keys always
    # line up 1:1 with STATUS_TYPE_IMMUNITIES keys.
    original_format = games_module.format_status_log_label
    monkeypatch.setattr(games_module, "format_status_log_label", lambda status: "custom label")
    _run(["self:status:condition:type:poison:status:poison"], attacker, [], db, game, state)
    _run(["target:status:condition:type:poison:status:poison"], attacker, [target], db, game, state)
    monkeypatch.setattr(games_module, "format_status_log_label", original_format)


def test_status_plain_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db, attacker_types=["Poison"], target_types=["Poison"])

    # len(parts) < 3 -> continue.
    _run(["self:status"], attacker, [], db, game, state)

    monkeypatch.setattr("random.randint", lambda a, b: 1)
    # accuracy ValueError -> pass.
    _run(["self:status:poison:bad"], attacker, [], db, game, state)
    # accuracy miss -> continue.
    monkeypatch.setattr("random.randint", lambda a, b: 100)
    _run(["self:status:poison:0"], attacker, [], db, game, state)
    monkeypatch.setattr("random.randint", lambda a, b: 1)

    # self recipient immune by type -> "wasn't poisoned" branch.
    _run(["self:status:poison"], attacker, [], db, game, state)
    # target recipient immune by type -> "wasn't poisoned" branch.
    _run(["target:status:poison"], attacker, [target], db, game, state)
    # self recipient, applies successfully (Normal type, not poison-immune).
    normal_def = _make_unit_def(db, f"Plain Status Normal {next(_link_counter)}", types=["Normal"])
    normal_attacker = _make_game_unit(db, normal_def, x=3, y=3, hp=50, max_hp=50, game=game, user_id=attacker.user_id)
    _run(["self:status:burn"], normal_attacker, [], db, game, state)
    # target recipient, applies successfully.
    normal_target = _make_game_unit(db, normal_def, x=3, y=4, hp=50, max_hp=50, game=game, user_id=target.user_id)
    _run(["target:status:burn"], attacker, [normal_target], db, game, state)

    # Force "wasn't affected" fallback branches for both self and target.
    original_format = games_module.format_status_log_label
    monkeypatch.setattr(games_module, "format_status_log_label", lambda status: "custom label")
    _run(["self:status:poison"], attacker, [], db, game, state)
    _run(["target:status:poison"], attacker, [target], db, game, state)
    monkeypatch.setattr(games_module, "format_status_log_label", original_format)


# ---------------------------------------------------------------------------
# process_move_effects: safeguard edge branches
# ---------------------------------------------------------------------------


def test_safeguard_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)

    monkeypatch.setattr("random.randint", lambda a, b: 1)
    # accuracy ValueError -> pass.
    _run(["self:safeguard:bad"], attacker, [], db, game, state)
    # accuracy miss -> continue.
    monkeypatch.setattr("random.randint", lambda a, b: 100)
    _run(["self:safeguard:0"], attacker, [], db, game, state)
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    # target recipient, fainted target skipped.
    fainted_target = _make_game_unit(
        db, _make_unit_def(db, f"Safeguard Fainted {next(_link_counter)}"),
        x=2, y=2, hp=0, max_hp=50, game=game, user_id=target.user_id, is_fainted=True,
    )
    _run(["target:safeguard"], attacker, [fainted_target], db, game, state)
    # target recipient applies successfully.
    _run(["target:safeguard"], attacker, [target], db, game, state)


# ---------------------------------------------------------------------------
# process_move_effects: state / apply_state edge branches
# ---------------------------------------------------------------------------


def test_apply_state_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db, attacker_types=["Normal"], target_types=["Normal"])

    # len(parts) < 3 -> continue.
    _run(["self:state"], attacker, [], db, game, state)

    monkeypatch.setattr("random.randint", lambda a, b: 1)
    # condition-branch accuracy ValueError -> pass.
    _run(["self:state:condition:type:normal:confusion:bad"], attacker, [], db, game, state)
    # plain accuracy ValueError -> pass.
    _run(["self:state:confusion:bad"], attacker, [], db, game, state)
    # accuracy miss -> continue.
    monkeypatch.setattr("random.randint", lambda a, b: 100)
    _run(["self:state:confusion:0"], attacker, [], db, game, state)
    monkeypatch.setattr("random.randint", lambda a, b: 1)

    # self condition mismatch -> continue.
    _run(["self:state:condition:type:fire:confusion"], attacker, [], db, game, state)

    # SIDE_SCREEN branch: fainted target skipped, then wrong-owner skipped, then applied.
    fainted = _make_game_unit(
        db, _make_unit_def(db, f"State Fainted {next(_link_counter)}"),
        x=2, y=2, hp=0, max_hp=50, game=game, user_id=target.user_id, is_fainted=True,
    )
    other_user = _make_user(db, f"state-other-{next(_link_counter)}")
    wrong_owner = _make_game_unit(
        db, _make_unit_def(db, f"Wrong Owner {next(_link_counter)}"),
        x=2, y=3, hp=50, max_hp=50, game=game, user_id=other_user.id,
    )
    _run(["target:state:reflect"], attacker, [fainted, wrong_owner, target], db, game, state)

    # General target loop: fainted target skipped (non side-screen state).
    _run(["target:state:confusion"], attacker, [fainted], db, game, state)
    # target condition mismatch -> continue.
    fire_target = _make_game_unit(
        db, _make_unit_def(db, f"Fire Target {next(_link_counter)}", types=["Fire"]),
        x=2, y=4, hp=50, max_hp=50, game=game, user_id=target.user_id,
    )
    _run(["target:state:condition:type:water:confusion"], attacker, [fire_target], db, game, state)
    # confusion blocked by Safeguard on target -> continue.
    safe_target = _make_game_unit(
        db, _make_unit_def(db, f"Safe Confusion Target {next(_link_counter)}"),
        x=2, y=5, hp=50, max_hp=50, game=game, user_id=target.user_id, states=["safeguard", 3],
    )
    _run(["target:state:confusion"], attacker, [safe_target], db, game, state)
    # Successful plain state apply on target.
    _run(["target:state:confusion"], attacker, [target], db, game, state)


def test_apply_state_encore_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)
    monkeypatch.setattr("random.randint", lambda a, b: 1)

    move_used = models.Move(name="Tackle", type="Normal", category="Physical", power=40, pp=10, effects=[])
    db.add(move_used)
    db.commit()
    display_name = get_unit_display_name(target, db)

    # Replay log with the real "used <move>" entry FIRST (chronologically oldest)
    # and distractor entries (non-dict, non-system_log) AFTER it -- since the scan
    # walks the log in reverse, the distractors are encountered (and skipped via
    # their continue branches) before the real match is found.
    state.replay_log = [
        {"event": "system_log", "message": f"{display_name} used {move_used.name}"},
        {"event": "chat", "message": "hi"},
        "not-a-dict",
    ]
    db.add(state)
    db.commit()

    _run(["target:state:encore"], attacker, [target], db, game, state)
    db.commit()
    db.refresh(target)
    assert target.states[0] == "encore"

    # No matching last-move entry found -> "was unaffected" branch.
    target2 = _make_game_unit(
        db, _make_unit_def(db, f"Encore Target2 {next(_link_counter)}"),
        x=3, y=3, hp=50, max_hp=50, game=game, user_id=target.user_id,
    )
    state.replay_log = []
    db.add(state)
    db.commit()
    _run(["target:state:encore"], attacker, [target2], db, game, state)


# ---------------------------------------------------------------------------
# process_move_effects: copy_ability edge branches
# ---------------------------------------------------------------------------


def test_copy_ability_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)
    ability = models.Ability(name="Static", slug="static", description="desc", generation=1)
    db.add(ability)
    db.commit()

    # len(parts) < 3 -> continue.
    _run(["self:copy_ability"], attacker, [], db, game, state)
    # invalid source_ref -> continue.
    _run(["self:copy_ability:bogus"], attacker, [], db, game, state)
    # source_ref == "target" but no targets -> continue.
    _run(["self:copy_ability:target"], attacker, [], db, game, state)

    # source ability suppressed (gastro_acid) -> continue.
    suppressed_source = _make_game_unit(
        db, _make_unit_def(db, f"Suppressed Source {next(_link_counter)}", ability_ids=[ability.id]),
        x=3, y=3, hp=50, max_hp=50, game=game, user_id=target.user_id, states=["gastro_acid", 3],
    )
    set_unit_ability_id(suppressed_source, ability.id, db)
    db.commit()
    _run(["self:copy_ability:target"], attacker, [suppressed_source], db, game, state)

    # source ability id is None -> continue.
    no_ability_source = _make_game_unit(
        db, _make_unit_def(db, f"No Ability Source {next(_link_counter)}"),
        x=3, y=4, hp=50, max_hp=50, game=game, user_id=target.user_id,
    )
    _run(["self:copy_ability:target"], attacker, [no_ability_source], db, game, state)

    # source_ref == "self" (copy the attacker's own ability onto a target) with
    # recipient == "ally": game_id/user_id not int -> continue.
    set_unit_ability_id(attacker, ability.id, db)
    db.commit()
    unlinked_attacker = models.GameUnit(
        user_id=None, game_id=None, unit_id=attacker.unit_id, current_hp=50,
        current_stats={"hp": 50}, stat_boosts=default_stat_boosts(), flags={"ability_id": ability.id},
    )
    _run(["ally:copy_ability:self"], unlinked_attacker, [], db, game, state)

    # recipient == "ally": db.query(GameUnit) raises -> ally_units=[] caught by except.
    original_query = db.query

    def raising_query(model, *a, **kw):
        if model is models.GameUnit:
            raise RuntimeError("boom")
        return original_query(model, *a, **kw)

    db.query = raising_query
    try:
        _run(["ally:copy_ability:self"], attacker, [], db, game, state)
    finally:
        db.query = original_query

    # recipient == "ally": game.map_id invalid -> map_obj_local None -> continue.
    game.map_id = 999999
    db.add(game)
    db.commit()
    _run(["ally:copy_ability:self"], attacker, [], db, game, state)
    real_map_for_ally = _make_map(db, attacker.user_id)
    game.map_id = real_map_for_ally.id
    db.add(game)
    db.commit()

    # recipient == "ally": successful path (ally within move's affected tiles).
    ally = _make_game_unit(
        db, _make_unit_def(db, f"Ally Recipient {next(_link_counter)}"),
        x=0, y=0, hp=50, max_hp=50, game=game, user_id=attacker.user_id,
    )
    _run(["ally:copy_ability:self"], attacker, [], db, game, state)

    # recipient == "target": successful apply + log.
    _run(["target:copy_ability:self"], attacker, [target], db, game, state)


# ---------------------------------------------------------------------------
# process_move_effects: destiny_bond / laser_focus miss + hp<=0 skip branches
# (regression coverage for the destiny_bond/laser_focus indentation fix)
# ---------------------------------------------------------------------------


def test_destiny_bond_and_laser_focus_edge_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)

    # accuracy 0 -> always misses when random > 0.
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    _run(["self:destiny_bond:0"], attacker, [], db, game, state)
    _run(["self:laser_focus:0"], attacker, [], db, game, state)
    db.commit()
    db.refresh(attacker)
    assert attacker.states == []

    # accuracy ValueError -> pass, then hit path applies.
    _run(["self:destiny_bond:bad"], attacker, [], db, game, state)
    db.commit()
    db.refresh(attacker)
    assert attacker.states[0] == "destiny_bond"
    attacker.states = []
    db.add(attacker)
    db.commit()
    _run(["self:laser_focus:bad"], attacker, [], db, game, state)
    db.commit()
    db.refresh(attacker)
    assert attacker.states[0] == "laser_focus"

    # target recipient: fainted target skipped, then applied on alive target.
    fainted = _make_game_unit(
        db, _make_unit_def(db, f"Destiny Fainted {next(_link_counter)}"),
        x=2, y=2, hp=0, max_hp=50, game=game, user_id=target.user_id, is_fainted=True,
    )
    _run(["target:destiny_bond"], attacker, [fainted, target], db, game, state)
    db.commit()
    db.refresh(target)
    assert target.states[0] == "destiny_bond"

    target.states = []
    db.add(target)
    db.commit()
    _run(["target:laser_focus"], attacker, [fainted, target], db, game, state)
    db.commit()
    db.refresh(target)
    assert target.states[0] == "laser_focus"


# ---------------------------------------------------------------------------
# process_move_effects: heal (conditional + plain) edge branches
# ---------------------------------------------------------------------------


def test_heal_conditional_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)

    # denominator <=0 -> continue.
    _run(["self:heal:condition:weather:sun:0"], attacker, [], db, game, state)
    # denominator ValueError -> continue.
    _run(["self:heal:condition:weather:sun:bad"], attacker, [], db, game, state)
    # target recipient, no targets -> continue.
    _run(["target:heal:condition:weather:sun:2"], attacker, [], db, game, state)
    # weather condition doesn't match (no weather set) -> continue.
    _run(["self:heal:condition:weather:sun:2"], attacker, [], db, game, state)

    # Set up real weather tiles so condition matches for a "self" heal with Heal Block.
    game_map_state = models.GameMapState(
        game_id=game.id, map_id=game.map_id,
        weather_tiles=[[WEATHER_TO_ID["sun"]] * 3 for _ in range(3)],
        hazard_tiles=[[[] for _ in range(3)] for _ in range(3)],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[[0, 0] for _ in range(3)] for _ in range(3)],
        field_effect_tiles=[[0] * 3 for _ in range(3)],
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(game_map_state)
    db.commit()

    def _run_weather(effects, atk, tgts):
        process_move_effects(
            models.Move(name="Weather Heal", type="Normal", category="Status", effects=effects),
            atk, tgts, current_turn=0, db=db,
            weather_tiles=game_map_state.weather_tiles,
            game=game, game_state=state,
        )

    attacker.current_hp = 10
    attacker.states = ["heal_block", 3]
    db.add(attacker)
    db.commit()
    _run_weather(["self:heal:condition:weather:sun:2"], attacker, [])
    db.commit()
    db.refresh(attacker)
    assert attacker.current_hp == 10  # heal-blocked

    attacker.states = []
    db.add(attacker)
    db.commit()
    _run_weather(["self:heal:condition:weather:sun:2"], attacker, [])
    db.commit()
    db.refresh(attacker)
    assert attacker.current_hp > 10

    # target recipient: heal-blocked target skipped, then a healthy target heals.
    target.current_hp = 10
    target.states = ["heal_block", 3]
    db.add(target)
    db.commit()
    healthy_target = _make_game_unit(
        db, _make_unit_def(db, f"Weather Heal Target {next(_link_counter)}"),
        x=2, y=2, hp=10, max_hp=50, game=game, user_id=target.user_id,
    )
    _run_weather(["target:heal:condition:weather:sun:2"], attacker, [target, healthy_target])
    db.commit()
    db.refresh(target)
    db.refresh(healthy_target)
    assert target.current_hp == 10
    assert healthy_target.current_hp > 10

    # Dedup: weather heal only applies once per recipient per move.
    _run_weather(
        ["target:heal:condition:weather:sun:2", "target:heal:condition:weather:sun:2"],
        attacker, [healthy_target],
    )


def test_heal_plain_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)

    # len(parts) < 3 -> continue.
    _run(["self:heal"], attacker, [], db, game, state)
    # denominator <= 0 -> continue.
    _run(["self:heal:0"], attacker, [], db, game, state)
    # denominator ValueError -> continue.
    _run(["self:heal:bad"], attacker, [], db, game, state)

    # self heal success.
    attacker.current_hp = 10
    db.add(attacker)
    db.commit()
    _run(["self:heal:2"], attacker, [], db, game, state)
    db.commit()
    db.refresh(attacker)
    assert attacker.current_hp > 10

    # target heal: fainted target skipped, healthy target heals.
    target.current_hp = 10
    db.add(target)
    db.commit()
    fainted = _make_game_unit(
        db, _make_unit_def(db, f"Plain Heal Fainted {next(_link_counter)}"),
        x=2, y=2, hp=0, max_hp=50, game=game, user_id=target.user_id, is_fainted=True,
    )
    _run(["target:heal:2"], attacker, [fainted, target], db, game, state)
    db.commit()
    db.refresh(target)
    assert target.current_hp > 10


# ---------------------------------------------------------------------------
# process_move_effects: cure_status edge branches
# ---------------------------------------------------------------------------


def test_cure_status_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)

    # len(parts) < 3 -> continue.
    _run(["self:cure_status"], attacker, [], db, game, state)

    attacker.status_effects = ["poison", 3]
    db.add(attacker)
    db.commit()
    _run(["self:cure_status:poison"], attacker, [], db, game, state)
    db.commit()
    db.refresh(attacker)
    assert attacker.status_effects == []

    # target recipient: fainted target skipped, healthy target cured.
    target.status_effects = ["burn", 3]
    db.add(target)
    db.commit()
    fainted = _make_game_unit(
        db, _make_unit_def(db, f"Cure Fainted {next(_link_counter)}"),
        x=2, y=2, hp=0, max_hp=50, game=game, user_id=target.user_id, is_fainted=True,
    )
    _run(["target:cure_status:burn"], attacker, [fainted, target], db, game, state)
    db.commit()
    db.refresh(target)
    assert target.status_effects == []


# ---------------------------------------------------------------------------
# process_move_effects: revive edge branches
# ---------------------------------------------------------------------------


def test_revive_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)

    # len(parts) < 3 -> continue.
    _run(["target:revive"], attacker, [target], db, game, state)
    # recipient != "target" -> continue.
    _run(["self:revive:2"], attacker, [], db, game, state)
    # hp_denominator <= 0 -> continue.
    _run(["target:revive:0"], attacker, [target], db, game, state)
    # hp_denominator ValueError -> continue.
    _run(["target:revive:bad"], attacker, [target], db, game, state)

    # attacker heal-blocked -> continue.
    attacker.states = ["heal_block", 3]
    db.add(attacker)
    db.commit()
    _run(["target:revive:2"], attacker, [target], db, game, state)
    attacker.states = []
    db.add(attacker)
    db.commit()

    # game.map_id invalid -> map_obj None -> continue.
    game.map_id = 999999
    db.add(game)
    db.commit()
    _run(["target:revive:2"], attacker, [target], db, game, state)
    real_map = _make_map(db, attacker.user_id)
    game.map_id = real_map.id
    db.add(game)
    db.commit()

    # target not fainted and hp > 0 -> skip (continue).
    _run(["target:revive:2"], attacker, [target], db, game, state)

    # target wrong owner -> skip (continue).
    other_user = _make_user(db, f"revive-other-{next(_link_counter)}")
    other_fainted = _make_game_unit(
        db, _make_unit_def(db, f"Other Fainted {next(_link_counter)}"),
        x=1, y=1, hp=0, max_hp=50, game=game, user_id=other_user.id, is_fainted=True,
    )
    _run(["target:revive:2"], attacker, [other_fainted], db, game, state)

    # placement is None (map fully occupied) -> log "couldn't be revived" + continue.
    fainted_same_owner = _make_game_unit(
        db, _make_unit_def(db, f"Same Owner Fainted {next(_link_counter)}"),
        x=1, y=1, hp=0, max_hp=50, game=game, user_id=attacker.user_id, is_fainted=True,
    )
    original_find = games_module.find_revival_placement_tile
    try:
        games_module.find_revival_placement_tile = lambda *a, **kw: None
        _run(["target:revive:2"], attacker, [fainted_same_owner], db, game, state)
    finally:
        games_module.find_revival_placement_tile = original_find

    # successful revive, including the GamePlayer.game_units append branch.
    player_state = models.GamePlayer(game_id=game.id, player_id=attacker.user_id, cash_remaining=0, game_units=[])
    db.add(player_state)
    db.commit()
    _run(["target:revive:2"], attacker, [fainted_same_owner], db, game, state)
    db.commit()
    db.refresh(fainted_same_owner)
    db.refresh(player_state)
    assert fainted_same_owner.is_fainted is False
    assert fainted_same_owner.id in (player_state.game_units or [])


# ---------------------------------------------------------------------------
# apply_damage_based_move_effects edge branches
# ---------------------------------------------------------------------------


def test_apply_damage_based_move_effects_edge_branches(db):
    from app.routes.games import apply_damage_based_move_effects

    game, state, attacker, target = _stat_setup(db)

    # No move.effects -> returns [] immediately (already covered elsewhere, sanity only).
    assert apply_damage_based_move_effects(
        models.Move(name="No Effects", type="Normal", category="Physical", effects=[]),
        attacker, [target], [], db,
    ) == []

    # drain: effect_amount <= 0 (zero total damage dealt) -> continue.
    move_drain = models.Move(name="Drain Zero", type="Normal", category="Physical", effects=["self:drain:2"])
    apply_damage_based_move_effects(move_drain, attacker, [target], [{"id": target.id, "damage": 0}], db)

    # drain: apply_to_unit early-return because the recipient is already fainted.
    attacker.current_hp = 0
    db.add(attacker)
    db.commit()
    move_drain2 = models.Move(name="Drain Fainted", type="Normal", category="Physical", effects=["self:drain:2"])
    apply_damage_based_move_effects(move_drain2, attacker, [target], [{"id": target.id, "damage": 100}], db)
    attacker.current_hp = 50
    db.add(attacker)
    db.commit()

    # drain: max_hp <= 0 -> return (no-op) even though recipient is alive.
    attacker.current_stats = {"hp": 0}
    db.add(attacker)
    db.commit()
    apply_damage_based_move_effects(move_drain2, attacker, [target], [{"id": target.id, "damage": 100}], db)
    attacker.current_stats = {"hp": 50}
    db.add(attacker)
    db.commit()

    # recoil: denominator <= 0 -> continue.
    move_recoil_bad_denom = models.Move(
        name="Recoil Bad Denom", type="Normal", category="Physical", effects=["self:recoil:damage_dealt:0"]
    )
    apply_damage_based_move_effects(move_recoil_bad_denom, attacker, [target], [{"id": target.id, "damage": 20}], db)

    # recoil: invalid recipient -> recipients empty -> continue.
    move_recoil_bad_recipient = models.Move(
        name="Recoil Bad Recipient", type="Normal", category="Physical", effects=["ally:recoil:damage_dealt:2"]
    )
    apply_damage_based_move_effects(move_recoil_bad_recipient, attacker, [target], [{"id": target.id, "damage": 20}], db)

    # recoil: maximum_hp basis with max_hp <= 0 -> continue for that unit.
    attacker.current_stats = {"hp": 0}
    db.add(attacker)
    db.commit()
    move_recoil_maxhp = models.Move(
        name="Recoil MaxHP", type="Normal", category="Physical", effects=["self:recoil:maximum_hp:2"]
    )
    apply_damage_based_move_effects(move_recoil_maxhp, attacker, [target], [{"id": target.id, "damage": 20}], db)
    attacker.current_stats = {"hp": 50}
    db.add(attacker)
    db.commit()

    # recoil: fainting path with faint_logged_ids tracking (covers the
    # "publish once, then remember" branch).
    attacker.current_hp = 5
    db.add(attacker)
    db.commit()
    faint_logged_ids: set[int] = set()
    move_recoil_fatal = models.Move(
        name="Recoil Fatal", type="Normal", category="Physical", effects=["self:recoil:damage_dealt:1"]
    )
    fainted_ids = apply_damage_based_move_effects(
        move_recoil_fatal, attacker, [target], [{"id": target.id, "damage": 100}], db,
        game=game, game_state=state, faint_logged_ids=faint_logged_ids,
    )
    assert attacker.id in fainted_ids
    assert attacker.id in faint_logged_ids


# ---------------------------------------------------------------------------
# decrement_and_expire_stat_boosts / decrement_and_expire_status_effects /
# decrement_and_expire_hazards edge branches
# ---------------------------------------------------------------------------


def test_decrement_and_expire_stat_boosts_edge_branches(db):
    from app.routes.games import decrement_and_expire_stat_boosts

    game, state, attacker, target = _stat_setup(db)
    attacker.stat_boosts = {
        "attack": "not-a-list",  # non-list value -> continue for this stat
        "defense": [{"magnitude": 1, "expires_turn": 2}],  # decremented, stays (expires_turn=1>0)
        "speed": [{"magnitude": 1, "expires_turn": 1}],  # decremented to 0 -> filtered out
    }
    db.add(attacker)
    db.commit()

    modified_ids = decrement_and_expire_stat_boosts(attacker.user_id, game.id, db)
    assert attacker.id in modified_ids
    db.commit()
    db.refresh(attacker)
    assert attacker.stat_boosts["defense"][0]["expires_turn"] == 1
    assert attacker.stat_boosts["speed"] == []

    # No modification needed -> unit id not appended.
    other_attacker = _make_game_unit(
        db, _make_unit_def(db, f"No Boosts Mon {next(_link_counter)}"),
        x=2, y=2, hp=50, max_hp=50, game=game, user_id=attacker.user_id,
    )
    modified_ids2 = decrement_and_expire_stat_boosts(attacker.user_id, game.id, db)
    assert other_attacker.id not in modified_ids2


def test_decrement_and_expire_status_effects_extra_edge_branches(db):
    from app.routes.games import decrement_and_expire_status_effects

    game, state, attacker, target = _stat_setup(db)

    # Nightmare cleared when sleep expires, with game/game_state -> publishes log.
    attacker.status_effects = ["sleep", 1]
    attacker.states = ["nightmare", 3]
    db.add(attacker)
    db.commit()
    decrement_and_expire_status_effects(attacker.user_id, game.id, db, game=game, game_state=state)
    db.commit()
    db.refresh(attacker)
    assert attacker.states == []

    # Confusion expiring this tick -> "no longer confused" log with game/game_state.
    confusion_unit = _make_game_unit(
        db, _make_unit_def(db, f"Confused Mon {next(_link_counter)}"),
        x=2, y=2, hp=50, max_hp=50, game=game, user_id=attacker.user_id, states=["confusion", 1],
    )
    decrement_and_expire_status_effects(attacker.user_id, game.id, db, game=game, game_state=state)
    db.commit()
    db.refresh(confusion_unit)
    assert confusion_unit.states == []

    # Drowsy expiring -> attempt to apply sleep + log (with game/game_state), since no current status.
    drowsy_unit = _make_game_unit(
        db, _make_unit_def(db, f"Drowsy Mon {next(_link_counter)}"),
        x=2, y=3, hp=50, max_hp=50, game=game, user_id=attacker.user_id, states=["drowsy", 1],
    )
    decrement_and_expire_status_effects(attacker.user_id, game.id, db, game=game, game_state=state)
    db.commit()
    db.refresh(drowsy_unit)
    assert drowsy_unit.status_effects[0] == "sleep"

    # Active (non-expiring) flinch state -> can_move forced False.
    flinch_unit = _make_game_unit(
        db, _make_unit_def(db, f"Flinch Mon {next(_link_counter)}"),
        x=2, y=4, hp=50, max_hp=50, game=game, user_id=attacker.user_id, states=["flinch", 3], can_move=True,
    )
    decrement_and_expire_status_effects(attacker.user_id, game.id, db, game=game, game_state=state)
    db.commit()
    db.refresh(flinch_unit)
    assert flinch_unit.can_move is False


def test_decrement_and_expire_hazards_edge_branches(db):
    from app.routes.games import decrement_and_expire_hazards

    game, state, attacker, target = _stat_setup(db)
    real_map = db.query(models.Map).filter_by(id=game.map_id).first()
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=real_map.id,
        weather_tiles=[[0] * 3 for _ in range(3)],
        # Row 0 is malformed (not a list); row 1 has a hazard entry that
        # normalizes cleanly and decrements but stays active (turns_remaining>0
        # after decrement); row 2 has an entry expiring this tick.
        hazard_tiles=["not-a-list", [[[FIELD_HAZARD_TO_ID["spikes"], 3]], [], []], [[[FIELD_HAZARD_TO_ID["spikes"], 1]], [], []]],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[[0, 0] for _ in range(3)] for _ in range(3)],
        field_effect_tiles=[[0] * 3 for _ in range(3)],
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(map_state)
    db.commit()

    changed = decrement_and_expire_hazards(game.id, db)
    assert changed is True
    db.commit()
    db.refresh(map_state)
    assert map_state.hazard_tiles[0] == []
    assert map_state.hazard_tiles[1][0] == [[FIELD_HAZARD_TO_ID["spikes"], 2]]
    assert map_state.hazard_tiles[2][0] == []


def test_decrement_and_expire_hazards_normalization_changed_branch(db):
    """A malformed hazard entry that gets dropped during normalization should
    still mark the grid as changed even though decrement-driven expiry didn't
    cause it."""
    from app.routes.games import decrement_and_expire_hazards

    game, state, attacker, target = _stat_setup(db)
    real_map = db.query(models.Map).filter_by(id=game.map_id).first()
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=real_map.id,
        weather_tiles=[[0] * 3 for _ in range(3)],
        hazard_tiles=[[[["not-an-int", 3]], [], []], [[], [], []], [[], [], []]],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[[0, 0] for _ in range(3)] for _ in range(3)],
        field_effect_tiles=[[0] * 3 for _ in range(3)],
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(map_state)
    db.commit()

    changed = decrement_and_expire_hazards(game.id, db)
    assert changed is True


# ---------------------------------------------------------------------------
# apply_end_of_round_weather_damage edge branches
# ---------------------------------------------------------------------------


def test_apply_end_of_round_weather_damage_edge_branches(db):
    from app.routes.games import apply_end_of_round_weather_damage

    game, state, attacker, target = _stat_setup(db)

    # current_hp <= 0 -> skip in the first (weather chip damage) loop.
    fainted_unit = _make_game_unit(
        db, _make_unit_def(db, f"Weather Fainted {next(_link_counter)}"),
        x=0, y=0, hp=0, max_hp=50, game=game, user_id=attacker.user_id, is_fainted=True,
    )
    # aqua_ring/ingrain: hp <= 0 -> skip in the second loop.
    fainted_aqua = _make_game_unit(
        db, _make_unit_def(db, f"Aqua Fainted {next(_link_counter)}"),
        x=0, y=1, hp=0, max_hp=50, game=game, user_id=attacker.user_id, is_fainted=True, states=["aqua_ring", 5],
    )
    # aqua_ring: max_hp <= 0 -> continue.
    zero_maxhp_aqua = _make_game_unit(
        db, _make_unit_def(db, f"Aqua ZeroMax {next(_link_counter)}"),
        x=0, y=2, hp=10, max_hp=50, game=game, user_id=attacker.user_id, states=["aqua_ring", 5],
        current_stats_extra={"hp": 0},
    )
    db.add_all([fainted_unit, fainted_aqua, zero_maxhp_aqua])
    db.commit()
    apply_end_of_round_weather_damage(game.id, db)

    # cursed: max_hp <= 0 -> continue.
    zero_maxhp_cursed = _make_game_unit(
        db, _make_unit_def(db, f"Cursed ZeroMax {next(_link_counter)}"),
        x=1, y=1, hp=10, max_hp=50, game=game, user_id=attacker.user_id, states=["cursed", 5],
        current_stats_extra={"hp": 0},
    )
    # cursed: before_hp <= 0 -> continue.
    fainted_cursed = _make_game_unit(
        db, _make_unit_def(db, f"Cursed Fainted {next(_link_counter)}"),
        x=1, y=2, hp=0, max_hp=50, game=game, user_id=attacker.user_id, is_fainted=True, states=["cursed", 5],
    )
    # nightmare: asleep, max_hp <= 0 -> continue.
    zero_maxhp_nightmare = _make_game_unit(
        db, _make_unit_def(db, f"Nightmare ZeroMax {next(_link_counter)}"),
        x=2, y=0, hp=10, max_hp=50, game=game, user_id=attacker.user_id, states=["nightmare", 5],
        status_effects=["sleep", 3], current_stats_extra={"hp": 0},
    )
    # nightmare: asleep, before_hp <= 0 -> continue.
    fainted_nightmare = _make_game_unit(
        db, _make_unit_def(db, f"Nightmare Fainted {next(_link_counter)}"),
        x=2, y=1, hp=0, max_hp=50, game=game, user_id=attacker.user_id, is_fainted=True,
        states=["nightmare", 5], status_effects=["sleep", 3],
    )
    # salt_cure: max_hp <= 0 -> continue.
    zero_maxhp_salt = _make_game_unit(
        db, _make_unit_def(db, f"Salt ZeroMax {next(_link_counter)}"),
        x=2, y=2, hp=10, max_hp=50, game=game, user_id=attacker.user_id, states=["salt_cure", 5],
        current_stats_extra={"hp": 0},
    )
    # salt_cure: before_hp <= 0 -> continue.
    fainted_salt = _make_game_unit(
        db, _make_unit_def(db, f"Salt Fainted {next(_link_counter)}"),
        x=0, y=0, hp=0, max_hp=50, game=game, user_id=attacker.user_id, is_fainted=True, states=["salt_cure", 5],
    )

    apply_end_of_round_weather_damage(game.id, db)


def test_apply_end_of_round_aqua_ring_heal_block_branch(db, monkeypatch):
    """The production code re-derives Heal Block via a second normalize_states(unit.states)
    call *after* already branching on state_effect[0] in {"aqua_ring", "ingrain"} -- since
    a unit can only hold one active state at a time in this data model, the two reads are
    always identical in real gameplay. We simulate an aqua_ring unit whose Heal Block flag
    is (re)detected on that second read to exercise this defensive branch (games.py lines
    ~4646-4650).
    """
    from app.routes.games import apply_end_of_round_weather_damage

    game, state, attacker, target = _stat_setup(db)
    aqua_unit = _make_game_unit(
        db, _make_unit_def(db, f"Aqua HealBlock Solo {next(_link_counter)}"),
        x=0, y=0, hp=10, max_hp=50, game=game, user_id=attacker.user_id, states=["aqua_ring", 5],
    )
    # Remove the other _stat_setup units from this game so only aqua_unit is processed.
    db.delete(attacker)
    db.delete(target)
    db.commit()

    call_results = iter([["aqua_ring", 5], ["heal_block", 5]])
    monkeypatch.setattr(games_module, "normalize_states", lambda raw: next(call_results))

    modified = apply_end_of_round_weather_damage(game.id, db)
    assert aqua_unit.id not in modified
    db.commit()
    db.refresh(aqua_unit)
    assert aqua_unit.current_hp == 10  # unhealed due to Heal Block


# ---------------------------------------------------------------------------
# apply_end_of_round_stump_tile_effects edge branches
# ---------------------------------------------------------------------------


def test_apply_end_of_round_stump_tile_effects_edge_branches(db):
    from app.routes.games import apply_end_of_round_stump_tile_effects

    user = _make_user(db, f"stump-user-{next(_link_counter)}")
    map_obj = _make_map(db, user.id, special_tiles=[["stump", None, None], [None, None, None], [None, None, None]])
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    grass_def = _make_unit_def(db, f"Stump Grass Mon {next(_link_counter)}", types=["Grass"])
    normal_def = _make_unit_def(db, f"Stump Normal Mon {next(_link_counter)}", types=["Normal"])

    # current_hp <= 0 -> skip.
    fainted = _make_game_unit(db, grass_def, x=0, y=0, hp=0, max_hp=50, game=game, user_id=user.id, is_fainted=True)
    # not grass type -> skip.
    normal_unit = _make_game_unit(db, normal_def, x=0, y=0, hp=40, max_hp=50, game=game, user_id=user.id)
    # grass type, on stump, but max_hp <= 0 -> continue.
    zero_maxhp_grass = _make_game_unit(
        db, grass_def, x=0, y=0, hp=10, max_hp=50, game=game, user_id=user.id, current_stats_extra={"hp": 0},
    )
    # grass type, on stump, healthy -> heals successfully.
    healthy_grass = _make_game_unit(db, grass_def, x=0, y=0, hp=10, max_hp=50, game=game, user_id=user.id)

    modified = apply_end_of_round_stump_tile_effects(game.id, db)
    assert healthy_grass.id in modified
    assert normal_unit.id not in modified
    assert fainted.id not in modified
    assert zero_maxhp_grass.id not in modified


# ---------------------------------------------------------------------------
# apply_end_of_round_entry_hazard_effects edge branches
# ---------------------------------------------------------------------------


def test_apply_end_of_round_entry_hazard_effects_edge_branches(db, monkeypatch):
    from app.routes.games import apply_end_of_round_entry_hazard_effects

    game, state, attacker, target = _stat_setup(db, attacker_types=["Poison"])
    real_map = db.query(models.Map).filter_by(id=game.map_id).first()
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=real_map.id,
        weather_tiles=[[0] * 3 for _ in range(3)],
        hazard_tiles=[[[[FIELD_HAZARD_TO_ID["toxic_spikes"], 5]], [], []], [[], [], []], [[], [], []]],
        room_effect_tiles=[[0] * 3 for _ in range(3)],
        terrain_effect_tiles=[[[0, 0] for _ in range(3)] for _ in range(3)],
        field_effect_tiles=[[0] * 3 for _ in range(3)],
        item_id_tiles=[[None] * 3 for _ in range(3)],
    )
    db.add(map_state)
    db.commit()

    # current_hp <= 0 -> skip.
    fainted = _make_game_unit(
        db, _make_unit_def(db, f"Hazard Fainted {next(_link_counter)}", types=["Poison"]),
        x=0, y=0, hp=0, max_hp=50, game=game, user_id=attacker.user_id, is_fainted=True,
    )

    # attacker (Poison type) standing on toxic_spikes is immune -> "wasn't affected" branch
    # forced via a monkeypatched label (STATUS_LOG_LABELS keys always line up with the
    # poisoned/burned/etc set under real data, so we simulate a mismatched label here).
    attacker.current_x, attacker.current_y = 0, 0
    db.add(attacker)
    db.commit()
    original_format = games_module.format_status_log_label
    monkeypatch.setattr(games_module, "format_status_log_label", lambda status: "custom label")
    apply_end_of_round_entry_hazard_effects(game.id, 0, db)
    monkeypatch.setattr(games_module, "format_status_log_label", original_format)


# ---------------------------------------------------------------------------
# Misc pure-helper edge branches (lines ~560-1610)
# ---------------------------------------------------------------------------


def test_resolve_move_pp_index_and_consume_item_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)
    unit_info = attacker.unit
    # move_id not equipped and not the held TM move -> None.
    assert games_module.resolve_move_pp_index(attacker, unit_info, 999999, db) is None

    # consume_unit_held_item: item_type filter mismatch -> False.
    games_module.set_unit_held_item(attacker, "Oran Berry", db)
    db.commit()
    assert games_module.consume_unit_held_item(attacker, db, item_type="gem") is False


def test_unit_stat_stage_helper_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)
    # No positive stat stages -> False.
    assert games_module.unit_has_positive_stat_stage(attacker) is False

    flags = games_module.get_unit_flags(attacker)
    flags["stat_stages_at_turn_start"] = {stat: 0 for stat in games_module.ALL_STAT_EFFECT_KEYS}
    games_module.set_unit_flags(attacker, flags, db)
    db.commit()
    db.refresh(attacker)
    # Snapshot exists but no stat has moved -> both False.
    assert games_module.unit_stats_lowered_since_turn_start(attacker) is False
    assert games_module.unit_stats_raised_since_turn_start(attacker) is False


def test_increment_allies_defeated_invalid_ids_noop(db):
    game, state, attacker, target = _stat_setup(db)
    attacker.game_id = None
    games_module.increment_allies_defeated_since_turn(attacker, db)  # no-op, does not raise


def test_move_has_revive_effect_false_when_no_match(db):
    move = models.Move(name="Tackle", type="Normal", category="Physical", effects=["self:destiny_bond"])
    assert games_module.move_has_revive_effect(move) is False


def test_get_unboosted_battle_stat_zero_when_stat_missing(db):
    game, state, attacker, target = _stat_setup(db)
    assert games_module.get_unboosted_battle_stat(attacker, "nonexistent_stat", db) == 0


def test_resolve_power_add_times_hit_bad_cap_ignored(db):
    move = models.Move(
        name="Rage Fist", type="Normal", category="Physical", power=50,
        effects=["power_add:times_hit:10:notanumber"],
    )
    game, state, attacker, target = _stat_setup(db)
    flags = games_module.get_unit_flags(attacker)
    flags["times_hit"] = 3
    games_module.set_unit_flags(attacker, flags, db)
    db.commit()
    db.refresh(attacker)
    # power_cap parse fails -> except: pass, but bonus from times_hit*per_unit still applied.
    assert games_module.resolve_power_add(move, attacker) == 30


def test_resolve_weather_move_multiplier_bad_override_falls_through(db):
    move = models.Move(
        name="Weather Ball", type="Normal", category="Special",
        effects=["weather_override:sun:notanumber"],
    )
    # ValueError on float(parts[2]) -> continue -> falls back to get_weather_move_multiplier.
    result = games_module.resolve_weather_move_multiplier_for_move(move, "normal", WEATHER_TO_ID["sun"])
    assert isinstance(result, float)


def test_normalize_timed_tile_cell_exception_branches():
    # len(cell) >= 2 but values aren't convertible -> except -> falls through to [0, 0].
    assert games_module.normalize_timed_tile_cell(["bad", "bad"]) == [0, 0]
    # len(cell) == 1 but not convertible -> except -> falls through to [0, 0].
    assert games_module.normalize_timed_tile_cell(["bad"]) == [0, 0]


def test_get_timed_effect_id_at_position_out_of_bounds():
    assert games_module.get_timed_effect_id_at_position([[1, 2]], 5, 0) == 0


def test_get_field_effect_at_position_edge_branches():
    # y >= len(tiles) -> 0.
    assert games_module.get_field_effect_at_position([[1, 2]], 0, 5) == 0
    # row not a list -> 0.
    assert games_module.get_field_effect_at_position([None], 0, 0) == 0
    # non-numeric cell value -> except -> 0.
    assert games_module.get_field_effect_at_position([["bad"]], 0, 0) == 0


def test_move_has_effect_token_false_for_none_move():
    assert games_module.move_has_effect_token(None, "target:sure_hit") is False


def test_resolve_power_multiplier_all_valueerror_and_super_effective_branches(db, monkeypatch):
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    game, state, attacker, target = _stat_setup(db, target_types=["Water"])
    effects = [
        "conditional_power:terrain:grassy:badfactor",
        "conditional_power:target_terrain:grassy:badfactor",
        "conditional_power:field:gravity:badfactor",
        "conditional_power:self:stat_lowered_since_turn:badfactor",
        "conditional_power:target_status:burn:badfactor",
        "conditional_power:target:has_status:badfactor",
        "conditional_power:super_effective:badfactor:x",
        "conditional_power:chance:badchance:badfactor",
        "conditional_power:weather:sun:badfactor",
    ]
    move = models.Move(name="Multi Cond", type="Electric", category="Special", effects=effects)
    result = games_module.resolve_power_multiplier(move, attacker, target, None, None, db)
    assert result == 1.0

    # super_effective success branch: Electric is super effective vs Water.
    move2 = models.Move(name="Thunder", type="Electric", category="Special", effects=["conditional_power:super_effective:2.0:x"])
    result2 = games_module.resolve_power_multiplier(move2, attacker, target, None, None, db)
    assert result2 == 2.0

    # chance branch success (random.randint patched to always return 1 <= any chance).
    move3 = models.Move(name="Chancy", type="Normal", category="Physical", effects=["conditional_power:chance:100:1.5"])
    result3 = games_module.resolve_power_multiplier(move3, attacker, target, None, None, db)
    assert result3 == 1.5

    # target None short-circuits target-dependent branches.
    move4 = models.Move(
        name="NoTarget", type="Normal", category="Physical",
        effects=["conditional_power:target_terrain:grassy:2", "conditional_power:field:gravity:2",
                 "conditional_power:target_status:burn:2", "conditional_power:super_effective:2:x"],
    )
    result4 = games_module.resolve_power_multiplier(move4, attacker, None, None, None, db)
    assert result4 == 1.0


def test_get_scaling_hit_powers_bad_token_skipped():
    move = models.Move(name="Triple Kick", type="Fighting", category="Physical", effects=["multi_hit:scaling:10,bad,30"])
    assert games_module.get_scaling_hit_powers(move) == [10, 30]


def test_move_uses_separate_hit_accuracy_false_for_bad_move():
    assert games_module.move_uses_separate_hit_accuracy(None) is False


def test_get_move_hit_count_none_move_returns_one():
    assert games_module.get_move_hit_count(None) == 1


def test_get_move_hit_count_bad_max_hits_falls_back_to_min():
    move = models.Move(name="Fixed Hits", type="Normal", category="Physical", effects=["multi_hit:3:badmax"])
    assert games_module.get_move_hit_count(move) == 3


def test_validate_move_execution_bad_last_attacker_id_fails(db):
    game, state, attacker, target = _stat_setup(db)
    flags = games_module.get_unit_flags(attacker)
    flags["last_damage_attacker_id"] = "not-an-int"
    games_module.set_unit_flags(attacker, flags, db)
    db.commit()
    db.refresh(attacker)
    move = models.Move(
        name="Revenge Move", type="Normal", category="Physical",
        effects=["requires:last_damage_attacker"],
    )
    result = games_module.validate_move_execution(move, attacker, [], None, db)
    assert result == "But it failed"


def test_clear_terrain_at_position_guard_branches(db):
    game, state, attacker, target = _stat_setup(db)
    # map_state None -> no-op, no raise.
    games_module.clear_terrain_at_position(None, 0, 0, db)
    map_obj = db.query(models.Map).filter_by(id=game.map_id).first()
    map_state = _make_map_state(db, game, map_obj)
    # Out of bounds -> no-op, no raise.
    games_module.clear_terrain_at_position(map_state, 999, 999, db)


def test_clear_hazards_and_substitutes_on_tiles_edge_branches(db):
    game, state, attacker, target = _stat_setup(db)
    fake_map_state = MagicMock()
    fake_map_state.hazard_tiles = "not-a-list"
    assert games_module.clear_hazards_on_tiles(fake_map_state, [(0, 0)], db) is False

    # Empty affected tiles -> False.
    assert games_module.clear_substitutes_on_tiles(game.id, [], db) is False

    # Negative coords -> continue (skip) branch.
    attacker.current_x, attacker.current_y = -1, -1
    db.add(attacker)
    db.commit()
    assert games_module.clear_substitutes_on_tiles(game.id, [(0, 0)], db) is False


def test_find_revival_placement_tile_zero_size_map_and_fully_occupied(db):
    game, state, attacker, target = _stat_setup(db)
    zero_map = models.Map(
        name=f"Zero Map {next(_link_counter)}", creator_id=attacker.user_id, is_official=True,
        width=0, height=0, tileset_names=["grass"], tile_data={}, allowed_modes=["Conquest"],
        allowed_player_counts=[2],
    )
    db.add(zero_map)
    db.commit()
    assert games_module.find_revival_placement_tile(attacker, zero_map, db) is None

    # Fully occupied small map -> loop exhausts -> None.
    tiny_map = models.Map(
        name=f"Tiny Map {next(_link_counter)}", creator_id=attacker.user_id, is_official=True,
        width=1, height=1, tileset_names=["grass"], tile_data={}, allowed_modes=["Conquest"],
        allowed_player_counts=[2],
    )
    db.add(tiny_map)
    db.commit()
    attacker.current_x, attacker.current_y = 0, 0
    db.add(attacker)
    db.commit()
    assert games_module.find_revival_placement_tile(attacker, tiny_map, db, pulse=1) is None


# ---------------------------------------------------------------------------
# reconcile_playable_players / advance_turn_if_player_has_no_actions edge branches
# ---------------------------------------------------------------------------


def test_reconcile_playable_players_sets_current_turn_zero_when_in_progress(db):
    user_a = _make_user(db, f"recon-turn-a-{next(_link_counter)}")
    user_b = _make_user(db, f"recon-turn-b-{next(_link_counter)}")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = models.GameState(
        game_id=game.id, current_turn=None, status=models.GameStatus.in_progress,
        players=[user_a.id, user_b.id], replay_log=[],
    )
    db.add(state)
    db.commit()
    unit_def = _make_unit_def(db, f"ReconTurn Mon {next(_link_counter)}")
    _make_game_unit(db, unit_def, x=0, y=0, hp=10, max_hp=10, game=game, user_id=user_a.id)
    _make_game_unit(db, unit_def, x=1, y=0, hp=10, max_hp=10, game=game, user_id=user_b.id)

    playable, eliminated, completed = games_module.reconcile_playable_players(game, state, db)
    assert completed is False
    assert state.current_turn == 0


def test_advance_turn_single_player_faints_this_turn_completes_with_removed_ids(db):
    """Unit hp is already 0 (committed) but not yet flagged is_fainted, mimicking a
    unit that dropped to 0 HP moments earlier in the same turn; remove_fainted_units_from_play
    should pick it up fresh during the end-of-turn sweep."""
    from app.routes.games import advance_turn_if_player_has_no_actions

    user = _make_user(db, f"poison-solo-{next(_link_counter)}")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id], current_turn=0)
    unit_def = _make_unit_def(db, f"PoisonSolo Mon {next(_link_counter)}")
    unit = _make_game_unit(
        db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user.id, can_move=False,
    )

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user.id, db)
    assert completed is True
    assert turn_advanced is False
    assert removed_ids == [unit.id]
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user.id


def test_advance_turn_two_player_fresh_faint_eliminates_current_player(db):
    from app.routes.games import advance_turn_if_player_has_no_actions

    user_a = _make_user(db, f"poison-two-a-{next(_link_counter)}")
    user_b = _make_user(db, f"poison-two-b-{next(_link_counter)}")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=0)
    unit_def = _make_unit_def(db, f"PoisonTwo Mon {next(_link_counter)}")
    unit_a = _make_game_unit(
        db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user_a.id, can_move=False,
    )
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id, can_move=True)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user_a.id, db)
    assert completed is True
    assert turn_advanced is False
    assert unit_a.id in removed_ids
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user_b.id


def test_advance_turn_max_turns_completion_publishes_removed_ids(db):
    from app.routes.games import advance_turn_if_player_has_no_actions

    user_a = _make_user(db, f"maxturns-removed-a-{next(_link_counter)}")
    user_b = _make_user(db, f"maxturns-removed-b-{next(_link_counter)}")
    user_c = _make_user(db, f"maxturns-removed-c-{next(_link_counter)}")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id, user_c.id], max_turns=1)
    state = _make_state(db, game, [user_a.id, user_b.id, user_c.id], current_turn=1)
    unit_def = _make_unit_def(db, f"MaxTurnsRemoved Mon {next(_link_counter)}")
    unit_a = _make_game_unit(
        db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user_a.id, can_move=False,
    )
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id, can_move=True)
    _make_game_unit(db, unit_def, x=2, y=0, hp=40, max_hp=40, game=game, user_id=user_c.id, can_move=True)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user_a.id, db)
    assert completed is True
    assert turn_advanced is False
    assert unit_a.id in removed_ids
    db.refresh(state)
    assert state.status == models.GameStatus.completed


def test_advance_turn_normal_success_publishes_removed_ids(db):
    """A unit already fainted this turn but the acting player still has a second
    living unit, so the turn advances normally (no completion) while still needing
    to publish unit_removed events for the newly-removed unit."""
    from app.routes.games import advance_turn_if_player_has_no_actions

    user_a = _make_user(db, f"normaladvance-a-{next(_link_counter)}")
    user_b = _make_user(db, f"normaladvance-b-{next(_link_counter)}")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=0)
    unit_def = _make_unit_def(db, f"NormalAdvance Mon {next(_link_counter)}")
    _make_game_unit(db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user_a.id, can_move=False)
    _make_game_unit(db, unit_def, x=0, y=1, hp=40, max_hp=40, game=game, user_id=user_a.id, can_move=False)
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id, can_move=True)

    removed_ids, turn_advanced, completed = advance_turn_if_player_has_no_actions(game, state, user_a.id, db)
    assert completed is False
    assert turn_advanced is True
    assert len(removed_ids) >= 1


# ---------------------------------------------------------------------------
# get_type_multiplier / normalize_status_effects / normalize_states / apply_state_effect
# ---------------------------------------------------------------------------


class _StatesRaises:
    @property
    def states(self):
        raise RuntimeError("boom")


def test_get_type_multiplier_foresight_bypass_and_exception_branches(db):
    game, state, attacker, target = _stat_setup(db)
    # Immune matchup (Normal vs Ghost) + defender with an unrelated active state -> hard immune.
    target.states = ["taunt", 3]
    db.add(target)
    db.commit()
    db.refresh(target)
    result = games_module.get_type_multiplier("normal", (["ghost"], target, db))
    assert result == 0

    # Exception while reading defender_unit.states -> except -> return 0.
    result2 = games_module.get_type_multiplier("normal", (["ghost"], _StatesRaises(), db))
    assert result2 == 0


def test_normalize_status_effects_dict_and_list_edge_branches():
    # dict form: invalid status name -> None -> falls through to [].
    assert games_module.normalize_status_effects({"status": "not_a_real_status"}) == []
    # dict form: expires_turn not numeric -> defaults to 1.
    assert games_module.normalize_status_effects({"status": "poison", "expires_turn": "bad"}) == ["poison", 1]
    # dict form: badly_poisoned with non-numeric bad_poison_turn -> defaults to 1.
    result = games_module.normalize_status_effects({"status": "badly_poisoned", "expires_turn": 3, "bad_poison_turn": "bad"})
    assert result == ["badly_poisoned", 3, 1]
    # list form: expires_turn_raw not numeric -> canonical parse returns None (line hit),
    # but the backwards-compat per-entry fallback still finds "poison" as a bare string.
    assert games_module.normalize_status_effects(["poison", "bad"]) == ["poison", 1]
    # list form: badly_poisoned with non-numeric bad_poison_turn_raw -> defaults to 1.
    result2 = games_module.normalize_status_effects(["badly_poisoned", 3, "bad"])
    assert result2 == ["badly_poisoned", 3, 1]


def test_normalize_states_string_and_list_edge_branches():
    assert games_module.normalize_states("  ") == []
    assert games_module.normalize_states("confusion") == ["confusion", 1]
    # list len >= 2 but state empty string -> [].
    assert games_module.normalize_states(["", 3]) == []
    # list len >= 2 but turns_remaining not numeric -> [].
    assert games_module.normalize_states(["taunt", "bad"]) == []


def test_apply_state_effect_drowsy_duration_from_player_count(db):
    """Regression test for a real production bug: "drowsy" (applied by Yawn's
    target:apply_state:drowsy effect) was missing from VALID_STATE_EFFECTS, so
    apply_state_effect always rejected it and Yawn silently did nothing. Fixed by
    adding "drowsy" to VALID_STATE_EFFECTS."""
    game, state, attacker, target = _stat_setup(db)
    result = games_module.apply_state_effect(attacker, "drowsy", db)
    assert result is True
    assert attacker.states[0] == "drowsy"
    assert attacker.states[1] == 2 * len(state.players)


def test_apply_confusion_self_damage_publishes_log_event(db):
    game, state, attacker, target = _stat_setup(db)
    damage = games_module.apply_confusion_self_damage(attacker, db, game, state)
    assert damage >= 1


def test_get_unit_types_falls_back_to_unit_id_query(db):
    game, state, attacker, target = _stat_setup(db)
    attacker.unit_id = attacker.unit.id
    original_unit = attacker.unit
    # Simulate the ORM relationship not being populated by monkeypatching type() lookup.
    import app.db.models as models_module

    class _NoRelUnit:
        unit_id = attacker.unit_id
        unit = None
        game_id = attacker.game_id
        states = attacker.states

    fake = _NoRelUnit()
    types = games_module.get_unit_types(fake, db)
    assert types == {t.lower() for t in original_unit.types}


def test_get_unit_ability_names_query_exception_branch(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)
    games_module.set_unit_ability_id(attacker, 12345, db)
    db.commit()
    db.refresh(attacker)

    original_query = db.query

    def raising_query(model, *a, **kw):
        if model is models.Ability:
            raise RuntimeError("boom")
        return original_query(model, *a, **kw)

    monkeypatch.setattr(db, "query", raising_query)
    assert games_module.get_unit_ability_names(attacker, db) == set()


def test_is_ability_and_item_suppressed_exception_branches(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)
    monkeypatch.setattr(games_module, "normalize_states", MagicMock(side_effect=RuntimeError("boom")))
    assert games_module.is_ability_suppressed(attacker) is False
    assert games_module.is_item_suppressed(attacker) is False


def test_apply_status_effect_invalid_status_name(db):
    game, state, attacker, target = _stat_setup(db)
    assert games_module.apply_status_effect(attacker, "not_a_real_status", db) is False


def test_matches_effect_condition_empty_ability_lists(db):
    game, state, attacker, target = _stat_setup(db)
    assert games_module.matches_effect_condition(attacker, "has_ability", "   ,  ", db) is False
    assert games_module.matches_effect_condition(attacker, "not_has_ability", "   ,  ", db) is False


def test_normalize_stat_boosts_edge_branches():
    assert games_module.normalize_stat_boosts("not-a-dict") == games_module.default_stat_boosts()
    result = games_module.normalize_stat_boosts({
        "not_a_real_stat": [{"magnitude": 1, "expires_turn": 4}],
        "attack": [
            "not-a-dict",
            {"magnitude": "bad"},
            {"magnitude": 2, "expires_turn": "bad"},
        ],
    })
    assert "not_a_real_stat" not in result
    assert result["attack"] == [{"magnitude": 2, "expires_turn": 4}]


def test_get_stat_multiplier_and_stage_edge_branches():
    boosts = games_module.default_stat_boosts()
    assert games_module.get_stat_multiplier(boosts, "attack") == 1.0  # empty instances -> 1.0
    assert games_module.get_stat_multiplier(boosts, "nonexistent_stat") == 1.0  # stat not tracked -> 1.0
    assert games_module.get_stat_stage(boosts, "nonexistent_stat") == 0
    broken_boosts = games_module.default_stat_boosts()
    broken_boosts["attack"] = "not-a-list"
    assert games_module.get_stat_stage(broken_boosts, "attack") == 0


def test_get_accuracy_stage_multiplier_negative_branch():
    result = games_module.get_accuracy_stage_multiplier(0, 4)
    assert result == pytest.approx(3 / 7)


def test_move_has_high_crit_ratio_false_for_unrelated_move():
    move = models.Move(name="Tackle", type="Normal", category="Physical", effects=["self:destiny_bond"])
    assert games_module.move_has_high_crit_ratio(move) is False


def test_compute_fixed_damage_last_damage_received_bad_flag_value(db):
    game, state, attacker, target = _stat_setup(db)
    flags = games_module.get_unit_flags(attacker)
    flags["last_damage_amount"] = "not-an-int"
    games_module.set_unit_flags(attacker, flags, db)
    db.commit()
    db.refresh(attacker)
    result = games_module.compute_fixed_damage_effect("target:fixed_damage:last_damage_received:1.5", attacker, target)
    assert result == 0


def test_apply_fixed_damage_move_effects_multi_hit_breaks_on_faint(db):
    game, state, attacker, target = _stat_setup(db)
    target.current_hp = 5
    db.add(target)
    db.commit()
    move = models.Move(
        name="Fixed Multi", type="Normal", category="Physical",
        effects=["target:fixed_damage:10"],
    )
    results = games_module.apply_fixed_damage_move_effects(move, attacker, [target], db, hit_count=5)
    assert len(results) == 1
    assert results[0]["current_hp"] == 0


def test_attempt_critical_hit_extreme_stage_boundaries(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)
    attacker.stat_boosts["crit"] = [{"magnitude": -6, "expires_turn": 4}]
    db.add(attacker)
    db.commit()
    monkeypatch.setattr(games_module, "get_critical_hit_chance", lambda _stage: 0.0)
    assert games_module.attempt_critical_hit(attacker) is False  # crit_chance <= 0
    monkeypatch.setattr(games_module, "get_critical_hit_chance", lambda _stage: 1.0)
    assert games_module.attempt_critical_hit(attacker) is True


def test_compute_effective_stats_query_exception_and_range_skip_branch(db, monkeypatch):
    game, state, attacker, target = _stat_setup(db)

    original_query = db.query

    def raising_query(model, *a, **kw):
        if model is models.GameUnit:
            raise RuntimeError("boom")
        return original_query(model, *a, **kw)

    monkeypatch.setattr(db, "query", raising_query)
    stats = games_module.compute_effective_stats(attacker, db)
    assert isinstance(stats, dict)


def test_compute_effective_stats_no_speed_key_zero_range(db):
    game, state, attacker, target = _stat_setup(db)
    unit_info = db.query(models.Unit).filter_by(id=attacker.unit_id).first()
    unit_info.base_stats = {"hp": 60, "attack": 60}
    db.add(unit_info)
    db.commit()
    stats = games_module.compute_effective_stats(attacker, db)
    assert stats["range"] == 0


# ---------------------------------------------------------------------------
# _resolve_random_tm_tiles_for_game / _get_or_create_game_map_state / serialize_game_response
# ---------------------------------------------------------------------------


def test_resolve_random_tm_tiles_for_game_no_map_state(db):
    game, state, attacker, target = _stat_setup(db)
    map_state = db.query(models.GameMapState).filter_by(game_id=game.id).first()
    assert map_state is None
    assert games_module._resolve_random_tm_tiles_for_game(game, db) is False


def test_get_or_create_game_map_state_raises_when_map_missing(db):
    from fastapi import HTTPException

    game, state, attacker, target = _stat_setup(db)
    game.map_id = 999999
    db.add(game)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        games_module._get_or_create_game_map_state(game, db)
    assert exc_info.value.status_code == 500


def test_get_or_create_game_map_state_fixes_stale_map_id(db):
    game, state, attacker, target = _stat_setup(db)
    real_map = db.query(models.Map).filter_by(id=game.map_id).first()
    stale_map_state = models.GameMapState(
        game_id=game.id, map_id=999999,
        weather_tiles=[[0]*3 for _ in range(3)], hazard_tiles=[[[] for _ in range(3)] for _ in range(3)],
        room_effect_tiles=[[0]*3 for _ in range(3)], terrain_effect_tiles=[[[0,0] for _ in range(3)] for _ in range(3)],
        field_effect_tiles=[[0]*3 for _ in range(3)], item_id_tiles=[[None]*3 for _ in range(3)],
    )
    db.add(stale_map_state)
    db.commit()

    result = games_module._get_or_create_game_map_state(game, db)
    assert result.map_id == real_map.id


def test_serialize_game_response_raises_without_game_state(db):
    from fastapi import HTTPException

    user = _make_user(db, f"noserialize-{next(_link_counter)}")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    # No GameState row created.
    with pytest.raises(HTTPException) as exc_info:
        games_module.serialize_game_response(game, db)
    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# advance_if_expired edge branches
# ---------------------------------------------------------------------------


def test_advance_if_expired_completes_when_current_player_eliminated(db):
    from datetime import datetime, timezone, timedelta

    user_a = _make_user(db, f"expired-a-{next(_link_counter)}")
    user_b = _make_user(db, f"expired-b-{next(_link_counter)}")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=0)
    unit_def = _make_unit_def(db, f"Expired Mon {next(_link_counter)}")
    _make_game_unit(db, unit_def, x=0, y=0, hp=0, max_hp=40, game=game, user_id=user_a.id, can_move=False)
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id, can_move=True)
    state.turn_deadline = datetime.now(timezone.utc) - timedelta(seconds=10)

    result = games_module.advance_if_expired(game, state, db)
    assert result is True
    db.refresh(state)
    assert state.status == models.GameStatus.completed
    assert state.winner_id == user_b.id


def test_advance_if_expired_normal_turn_advance(db):
    from datetime import datetime, timezone, timedelta

    user_a = _make_user(db, f"expiredok-a-{next(_link_counter)}")
    user_b = _make_user(db, f"expiredok-b-{next(_link_counter)}")
    map_obj = _make_map(db, user_a.id)
    game = _make_game(db, map_obj, [user_a.id, user_b.id])
    state = _make_state(db, game, [user_a.id, user_b.id], current_turn=0)
    unit_def = _make_unit_def(db, f"ExpiredOk Mon {next(_link_counter)}")
    _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user_a.id, can_move=True)
    _make_game_unit(db, unit_def, x=1, y=0, hp=40, max_hp=40, game=game, user_id=user_b.id, can_move=True)
    state.turn_deadline = datetime.now(timezone.utc) - timedelta(seconds=10)

    result = games_module.advance_if_expired(game, state, db)
    assert result is True
    db.refresh(state)
    assert state.status == models.GameStatus.in_progress
    assert state.current_turn == 1


def test_compute_turn_locks_noop_when_no_playable_players(db):
    user = _make_user(db, f"turnlock-none-{next(_link_counter)}")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id], current_turn=0)
    # No units placed at all -> reconcile completes the game (0 playable players).
    games_module.compute_turn_locks(game, state, db)  # should not raise


# ---------------------------------------------------------------------------
# HTTP route guard-clause edge branches (reuses _create_battle_game)
# ---------------------------------------------------------------------------


def test_start_game_unsupported_gamemode_returns_400(client, db, http_user):
    map_obj = _make_map(db, http_user.id)
    game = _make_game(db, map_obj, [http_user.id])
    game.max_players = 1
    db.add(game)
    db.commit()
    state = models.GameState(game_id=game.id, current_turn=0, status=models.GameStatus.closed, players=[http_user.id], replay_log=[])
    db.add(state)
    db.commit()

    # The GameMode DB enum only defines the three "supported" values, so the
    # "Unsupported game mode" branch can only be exercised by mutating the
    # in-memory attribute directly (bypassing enum validation on write) and
    # relying on autoflush=False + identity-map reuse so start_game's fresh
    # `db.query(Game)` still observes our unvalidated in-memory value.
    game.gamemode = "Draft"

    resp = client.post(f"/games/start/{game.id}")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unsupported game mode"


def test_toggle_ready_state_unsupported_gamemode_returns_400(client, db, http_user):
    map_obj = _make_map(db, http_user.id)
    game = _make_game(db, map_obj, [http_user.id])
    state = models.GameState(game_id=game.id, current_turn=0, status=models.GameStatus.preparation, players=[http_user.id], replay_log=[])
    db.add(state)
    db.commit()

    game.gamemode = "Draft"

    resp = client.post(f"/games/{game.link}/player/ready")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This game mode does not support readiness toggling"


def test_get_game_by_link_removes_fainted_and_completes(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="getgame-completes-1")
    ctx["opponent_unit"].current_hp = 0
    ctx["opponent_unit"].is_fainted = False
    db.add(ctx["opponent_unit"])
    db.commit()

    resp = client.get("/games/getgame-completes-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["winner_id"] == http_user.id


def test_get_turnlock_no_state_returns_empty(client, db, http_user):
    map_obj = _make_map(db, http_user.id)
    game = _make_game(db, map_obj, [http_user.id])
    resp = client.get(f"/games/{game.link}/turnlock")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_get_turnlock_completed_now_returns_empty(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="turnlock-complete-1")
    ctx["opponent_unit"].current_hp = 0
    ctx["opponent_unit"].is_fainted = True
    db.add(ctx["opponent_unit"])
    db.commit()

    resp = client.get("/games/turnlock-complete-1/turnlock")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_end_turn_completed_via_reconcile_after_advance(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="endturn-complete-1")
    # Make the acting user's unit die from poison this same turn so remove_fainted
    # picks it up fresh, eliminating them mid-end_turn (after set_next_playable_turn).
    ctx["unit"].current_hp = 0
    db.add(ctx["unit"])
    db.commit()

    resp = client.post("/games/endturn-complete-1/end_turn")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Game completed"
    db.refresh(ctx["state"])
    assert ctx["state"].status == models.GameStatus.completed


def test_change_unit_item_preparation_gate_and_unit_not_found(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="itemgate-1")
    item = models.Item(name="Oran Berry", slug="oran-berry", category="berry", cost=10)
    db.add(item)
    db.commit()

    # Game is in_progress, not preparation -> 400.
    resp = client.post(f"/games/itemgate-1/units/{ctx['unit'].id}/item", json={"item_id": item.id})
    assert resp.status_code == 400

    ctx["state"].status = models.GameStatus.preparation
    db.add(ctx["state"])
    db.commit()

    # Unit not found (belongs to opponent) -> 404.
    resp2 = client.post(f"/games/itemgate-1/units/{ctx['opponent_unit'].id}/item", json={"item_id": item.id})
    assert resp2.status_code == 404


def test_change_unit_ability_preparation_gate_and_unit_not_found(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="abilitygate-1")
    ability = models.Ability(name="Static", slug="static", generation=1, description="d")
    db.add(ability)
    db.commit()

    resp = client.post(f"/games/abilitygate-1/units/{ctx['unit'].id}/ability", json={"ability_id": ability.id})
    assert resp.status_code == 400

    ctx["state"].status = models.GameStatus.preparation
    db.add(ctx["state"])
    db.commit()

    resp2 = client.post(f"/games/abilitygate-1/units/{ctx['opponent_unit'].id}/ability", json={"ability_id": ability.id})
    assert resp2.status_code == 404


def test_remove_unit_refunds_item_and_hidden_ability_cost(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="removeunit-1")
    item = models.Item(name="Leftovers", slug="leftovers", category="held", cost=50)
    ability = models.Ability(name="Levitate", slug="levitate", generation=3, description="d")
    db.add_all([item, ability])
    db.commit()
    unit_info = db.query(models.Unit).filter_by(id=ctx["unit"].unit_id).first()
    unit_info.ability_ids = [ability.id]
    unit_info.hidden_ability_id = ability.id
    db.add(unit_info)
    games_module.set_unit_held_item(ctx["unit"], item.slug, db)
    games_module.set_unit_ability_id(ctx["unit"], ability.id, db)
    db.commit()

    before_cash = ctx["player"].cash_remaining
    resp = client.delete(f"/games/removeunit-1/units/remove/{ctx['unit'].id}")
    assert resp.status_code == 200
    db.refresh(ctx["player"])
    assert ctx["player"].cash_remaining > before_cash


def _make_war_game_for_capture(db, http_user, link="warcapture-1"):
    ctx = _create_battle_game(db, http_user, link=link, gamemode="War")
    map_state = ctx["map_state"]
    width = ctx["map_obj"].width
    height = ctx["map_obj"].height
    objective_tiles = [[None for _ in range(width)] for _ in range(height)]
    objective_tiles[ctx["unit"].current_y][ctx["unit"].current_x] = {
        "kind": "capture_point",
        "owner": 2,
        "hp": 20,
        "max_hp": 20,
    }
    map_state.objective_tiles = objective_tiles
    db.add(map_state)
    db.commit()
    return ctx


def test_capture_objective_guard_clauses(client, db, http_user):
    resp = client.post("/games/no-such-link/war/capture", json={"unit_id": 1})
    assert resp.status_code == 404

    conquest_ctx = _create_battle_game(db, http_user, link="capture-not-war")
    resp = client.post("/games/capture-not-war/war/capture", json={"unit_id": conquest_ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Capture is only available in War mode"

    ctx = _make_war_game_for_capture(db, http_user)
    ctx["state"].status = models.GameStatus.preparation
    db.add(ctx["state"])
    db.commit()
    resp = client.post("/games/warcapture-1/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game not in progress"
    ctx["state"].status = models.GameStatus.in_progress
    db.add(ctx["state"])
    db.commit()

    # Not-your-turn: shift current_turn to point at opponent.
    ctx["state"].current_turn = 1
    db.add(ctx["state"])
    db.commit()
    resp = client.post("/games/warcapture-1/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 403
    ctx["state"].current_turn = 0
    db.add(ctx["state"])
    db.commit()

    # Unit not found.
    resp = client.post("/games/warcapture-1/war/capture", json={"unit_id": 999999})
    assert resp.status_code == 404

    # Map state missing.
    db.delete(ctx["map_state"])
    db.commit()
    resp = client.post("/games/warcapture-1/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Map state missing"


def test_capture_objective_completed_now_at_top_and_invalid_state(client, db, http_user, monkeypatch):
    ctx = _make_war_game_for_capture(db, http_user)
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], True))
    resp = client.post("/games/warcapture-1/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game completed"


def test_capture_objective_invalid_state(client, db, http_user, monkeypatch):
    ctx = _make_war_game_for_capture(db, http_user, link="warcapture-invalid")
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], False))
    resp = client.post("/games/warcapture-invalid/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game state"


def test_capture_objective_player_not_in_game(client, db, http_user, monkeypatch):
    ctx2 = _make_war_game_for_capture(db, http_user, link="warcapture-nopn")
    monkeypatch.setattr(games_module, "get_player_number", lambda *a, **k: None)
    resp = client.post("/games/warcapture-nopn/war/capture", json={"unit_id": ctx2["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Player not in game"


def test_capture_objective_not_on_objective_and_already_owned(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="warcapture-2", gamemode="War")
    resp = client.post("/games/warcapture-2/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit is not on an objective"

    map_state = ctx["map_state"]
    width = ctx["map_obj"].width
    height = ctx["map_obj"].height
    objective_tiles = [[None for _ in range(width)] for _ in range(height)]
    objective_tiles[ctx["unit"].current_y][ctx["unit"].current_x] = {
        "kind": "capture_point",
        "owner": 1,
        "hp": 20,
        "max_hp": 20,
    }
    map_state.objective_tiles = objective_tiles
    db.add(map_state)
    db.commit()
    resp = client.post("/games/warcapture-2/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "You already own this objective"


def test_capture_objective_completed_game_and_success_path(client, db, http_user, monkeypatch):
    ctx = _make_war_game_for_capture(db, http_user)

    # Force the second reconcile_playable_players call (after capture damage
    # is applied) to report completion, without tripping the earlier
    # top-of-function guard.
    real_reconcile = games_module.reconcile_playable_players
    call_count = {"n": 0}

    def fake_reconcile(game, state, db_):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            return [http_user.id], False, True
        return real_reconcile(game, state, db_)

    monkeypatch.setattr(games_module, "reconcile_playable_players", fake_reconcile)

    resp = client.post("/games/warcapture-1/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["game_completed"] is True


def test_capture_objective_success_advances_turn(client, db, http_user):
    ctx = _make_war_game_for_capture(db, http_user)
    resp = client.post("/games/warcapture-1/war/capture", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert "captured" in body
    assert body["game_completed"] is False


# ---------------------------------------------------------------------------
# wait_unit / pick_up_map_item / revert_unit_position / move_unit guards
# ---------------------------------------------------------------------------


def test_wait_unit_invalid_state(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="wait-final-1")
    # reconcile_playable_players always normalizes state.current_turn to 0 (and
    # completes the game whenever playable_players is empty), so the
    # `not playable_players or state.current_turn is None` guard below it can
    # only be reached by forcing reconcile_playable_players to return an
    # (empty, not-completed) result directly.
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], False))
    resp = client.post("/games/wait-final-1/wait", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game state"


def test_wait_unit_not_your_turn(client, db, http_user):
    ctx2 = _create_battle_game(db, http_user, link="wait-final-2")
    ctx2["state"].current_turn = 1
    db.add(ctx2["state"])
    db.commit()
    resp = client.post("/games/wait-final-2/wait", json={"unit_id": ctx2["unit"].id})
    assert resp.status_code == 403


def test_wait_unit_publishes_removed_ids(client, db, http_user):
    # 3-player game: http_user waits with their only unit (triggering an
    # end-of-turn sweep), a fresh-fainted opponent unit gets removed, but a
    # third player keeps the game going so `removed_ids` is non-empty
    # without completing the game (exercises the loop at line ~7607).
    ctx = _create_battle_game(db, http_user, link="wait-final-4")
    third_user = _make_user(db, "wait-third-player")
    third_unit = models.GameUnit(
        game_id=ctx["game"].id,
        unit_id=ctx["unit"].unit_id,
        user_id=third_user.id,
        starting_x=5,
        starting_y=5,
        current_x=5,
        current_y=5,
        level=50,
        current_hp=100,
        current_stats=dict(ctx["unit"].current_stats),
        stat_boosts=ctx["unit"].stat_boosts,
        status_effects=[],
        states=[],
        is_fainted=False,
        can_move=True,
        move_pp=[20],
        flags={},
    )
    db.add(third_unit)
    ctx["state"].players = [http_user.id, ctx["opponent"].id, third_user.id]
    db.add(ctx["state"])
    third_player = models.GamePlayer(
        game_id=ctx["game"].id, player_id=third_user.id, cash_remaining=1000,
        game_units=[third_unit.id], is_ready=True,
    )
    db.add(third_player)
    db.commit()

    ctx["opponent_unit"].current_hp = 0
    ctx["opponent_unit"].is_fainted = False
    db.add(ctx["opponent_unit"])
    db.commit()

    resp = client.post("/games/wait-final-4/wait", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert ctx["opponent_unit"].id in body["removed_ids"]
    assert body["turn_advanced"] is True


def test_pick_up_map_item_invalid_state_and_swap_paths(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="pickup-final-1")
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], False))
    resp = client.post("/games/pickup-final-1/pick_up_item", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game state"


def test_pick_up_map_item_swap_logs_and_publishes(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="pickup-final-2")
    item1 = models.Item(name="Oran Berry", slug="oran-berry", category="berry", cost=10)
    item2 = models.Item(name="Sitrus Berry", slug="sitrus-berry", category="berry", cost=20)
    db.add_all([item1, item2])
    db.commit()

    games_module.set_unit_held_item(ctx["unit"], item1.slug, db)
    db.commit()

    map_state = ctx["map_state"]
    x, y = ctx["unit"].current_x, ctx["unit"].current_y
    tiles = [list(row) for row in map_state.item_id_tiles]
    tiles[y][x] = item2.id
    map_state.item_id_tiles = tiles
    db.add(map_state)
    db.commit()

    resp = client.post("/games/pickup-final-2/pick_up_item", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["swapped"] is True
    assert body["item_slug"] == item2.slug


def test_pick_up_map_item_no_turn_advance_commits_directly(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="pickup-final-noadv")
    second_unit = models.GameUnit(
        game_id=ctx["game"].id,
        unit_id=ctx["unit"].unit_id,
        user_id=http_user.id,
        starting_x=2,
        starting_y=2,
        current_x=2,
        current_y=2,
        level=50,
        current_hp=100,
        current_stats=dict(ctx["unit"].current_stats),
        stat_boosts=ctx["unit"].stat_boosts,
        status_effects=[],
        states=[],
        is_fainted=False,
        can_move=True,
        move_pp=[20],
        flags={},
    )
    db.add(second_unit)
    db.commit()
    ctx["player"].game_units = [ctx["unit"].id, second_unit.id]
    db.add(ctx["player"])

    item1 = models.Item(name="Leftovers", slug="leftovers-noadv", category="held", cost=10)
    db.add(item1)
    db.commit()
    map_state = ctx["map_state"]
    x, y = ctx["unit"].current_x, ctx["unit"].current_y
    tiles = [list(row) for row in map_state.item_id_tiles]
    tiles[y][x] = item1.id
    map_state.item_id_tiles = tiles
    db.add(map_state)
    db.commit()

    resp = client.post("/games/pickup-final-noadv/pick_up_item", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["turn_advanced"] is False
    assert body["game_completed"] is False


def test_pick_up_map_item_completes_game_via_advance(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="pickup-final-3")
    item1 = models.Item(name="Leftovers", slug="leftovers-3", category="held", cost=10)
    db.add(item1)
    db.commit()
    map_state = ctx["map_state"]
    x, y = ctx["unit"].current_x, ctx["unit"].current_y
    tiles = [list(row) for row in map_state.item_id_tiles]
    tiles[y][x] = item1.id
    map_state.item_id_tiles = tiles
    db.add(map_state)
    db.commit()

    # Force advance_turn_if_player_has_no_actions (called after the pick-up)
    # to report a completed game, exercising the game_completed branch
    # without tripping the earlier top-of-function reconcile_playable_players
    # completed_now guard.
    monkeypatch.setattr(
        games_module,
        "advance_turn_if_player_has_no_actions",
        lambda *a, **k: ([ctx["opponent_unit"].id], False, True),
    )

    resp = client.post("/games/pickup-final-3/pick_up_item", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["game_completed"] is True


def test_revert_unit_position_invalid_state_guard(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="revert-final-1")
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], False))
    resp = client.post("/games/revert-final-1/revert_position", json={"unit_id": ctx["unit"].id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game state"


def test_move_unit_invalid_state(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="move-final-1")
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], False))
    resp = client.post("/games/move-final-1/move", json={"unit_id": ctx["unit"].id, "x": 0, "y": 0})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game state"


def test_move_unit_immobilized_check_exception_is_swallowed(client, db, http_user, monkeypatch, _mock_redis):
    ctx = _create_battle_game(db, http_user, link="move-final-exc")
    monkeypatch.setattr(games_module, "normalize_states", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    _mock_redis.hget.return_value = json.dumps({"tiles": [[0, 0]]})
    resp = client.post("/games/move-final-exc/move", json={"unit_id": ctx["unit"].id, "x": 0, "y": 0})
    # The immobilized check's exception is swallowed; the request proceeds
    # to the next guard (out of bounds / lock lookup) rather than 500ing.
    assert resp.status_code in (200, 400)


def test_move_unit_immobilized(client, db, http_user):
    ctx2 = _create_battle_game(db, http_user, link="move-final-2")
    ctx2["unit"].states = ["immobilized", 2]
    db.add(ctx2["unit"])
    db.commit()
    resp = client.post("/games/move-final-2/move", json={"unit_id": ctx2["unit"].id, "x": 0, "y": 0})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit is immobilized and cannot move"


def test_move_unit_final_tile_unoccupiable_after_slide(client, db, http_user, monkeypatch, _mock_redis):
    ctx = _create_battle_game(db, http_user, link="move-final-badtile", width=8, height=8)
    game = ctx["game"]
    unit = ctx["unit"]

    _mock_redis.hget.return_value = json.dumps({"tiles": [[2, 1], [3, 1]]})
    monkeypatch.setattr(games_module, "resolve_movement_destination", lambda *a, **k: (3, 1, True))

    calls = {"n": 0}

    def fake_occupy(*a, **k):
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr(games_module, "unit_can_occupy_tile", fake_occupy)

    resp = client.post("/games/move-final-badtile/move", json={"unit_id": unit.id, "x": 2, "y": 1})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This unit cannot move onto this tile"


def test_move_unit_sliding_locks_movement(client, db, http_user, monkeypatch, _mock_redis):
    ctx = _create_battle_game(db, http_user, link="move-final-3", width=8, height=8)
    game = ctx["game"]
    unit = ctx["unit"]

    _mock_redis.hget.return_value = json.dumps({"tiles": [[2, 1], [3, 1], [4, 1]]})

    monkeypatch.setattr(
        games_module,
        "resolve_movement_destination",
        lambda *a, **k: (3, 1, True),
    )

    resp = client.post("/games/move-final-3/move", json={"unit_id": unit.id, "x": 4, "y": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["x"] == 3 and body["y"] == 1


# ---------------------------------------------------------------------------
# execute_move: PP / move-knowledge guard clauses
# ---------------------------------------------------------------------------


def test_execute_move_unit_info_missing(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-noinfo")
    ctx["unit"].unit_id = 9_999_999
    db.add(ctx["unit"])
    db.commit()
    resp = client.post(
        "/games/exec-noinfo/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit has no moves"


def test_execute_move_no_equipped_moves(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-noequip")
    unit_info = db.query(models.Unit).filter_by(id=ctx["unit"].unit_id).first()
    unit_info.equipped_moves = []
    db.add(unit_info)
    ctx["unit"].flags = {}
    db.add(ctx["unit"])
    db.commit()
    resp = client.post(
        "/games/exec-noequip/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit has no moves"


def test_execute_move_does_not_know_move(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-unknownmove")
    other_move = models.Move(
        name="Unrelated Move", type="Normal", category="Status", power=None,
        accuracy=None, pp=10, effects=[], range="melee", targeting="self",
    )
    db.add(other_move)
    db.commit()
    resp = client.post(
        "/games/exec-unknownmove/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": other_move.id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit does not know this move"


def test_execute_move_pp_index_none_forced(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="exec-ppindexnone")
    # unit_knows_move and resolve_move_pp_index always agree in practice, so
    # force a mismatch to exercise the otherwise-unreachable defensive guard.
    monkeypatch.setattr(games_module, "resolve_move_pp_index", lambda *a, **k: None)
    resp = client.post(
        "/games/exec-ppindexnone/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit does not know this move"


def test_execute_move_pp_data_corrupted_forced(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="exec-ppcorrupt")
    # sync_tm_move_pp always resizes move_pp to match equipped moves, so force
    # it to a no-op to exercise the otherwise-unreachable corrupted-PP guard.
    monkeypatch.setattr(games_module, "sync_tm_move_pp", lambda *a, **k: None)
    ctx["unit"].move_pp = []
    db.add(ctx["unit"])
    db.commit()
    resp = client.post(
        "/games/exec-ppcorrupt/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "PP data corrupted"


def test_execute_move_no_pp_left(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-nopp")
    ctx["unit"].move_pp = [0]
    db.add(ctx["unit"])
    db.commit()
    resp = client.post(
        "/games/exec-nopp/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Move has no PP left"


# ---------------------------------------------------------------------------
# execute_move: ally / all targeting resolution branches
# ---------------------------------------------------------------------------


def _equip_extra_move(db, ctx, move):
    """Give the primary unit an additional equipped move (with full PP)."""
    ctx["unit"].flags = {"move_ids": [ctx["move"].id, move.id]}
    ctx["unit"].move_pp = [ctx["unit"].move_pp[0] if ctx["unit"].move_pp else 20, move.pp]
    db.add(ctx["unit"])
    db.commit()


def test_execute_move_ally_targeting_query_exception_is_swallowed(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="exec-allyexc")
    ally_move = models.Move(
        name="Ally Heal", type="Normal", category="Status", power=None,
        accuracy=None, pp=10, effects=[], range="ranged", targeting="ally",
    )
    db.add(ally_move)
    db.commit()
    _equip_extra_move(db, ctx, ally_move)

    original_query = db.query
    call_state = {"gu_count": 0}

    def fake_query(model, *a, **kw):
        if model is models.GameUnit:
            call_state["gu_count"] += 1
            if call_state["gu_count"] == 2:
                raise RuntimeError("boom")
        return original_query(model, *a, **kw)

    monkeypatch.setattr(db, "query", fake_query)

    resp = client.post(
        "/games/exec-allyexc/execute_move",
        json={
            "unit_id": ctx["unit"].id,
            "move_id": ally_move.id,
            "target_ids": [],
            "effect_tiles": [[ctx["unit"].current_x, ctx["unit"].current_y]],
        },
    )
    assert resp.status_code == 200


def test_execute_move_ally_targeting_skip_known_fainted_and_revive_branches(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-allytiles")
    ally_move = models.Move(
        name="Ally Heal 2", type="Normal", category="Status", power=None,
        accuracy=None, pp=10, effects=["target:heal:50"], range="ranged", targeting="ally",
    )
    db.add(ally_move)
    db.commit()
    _equip_extra_move(db, ctx, ally_move)

    # A second, already-known (via target_ids) ally at (2,2) -- should be skipped by
    # the known_target_ids check (line ~6822-6823) even though it's on an effect tile.
    known_ally = models.GameUnit(
        game_id=ctx["game"].id, unit_id=ctx["unit"].unit_id, user_id=http_user.id,
        starting_x=2, starting_y=2, current_x=2, current_y=2, level=50,
        current_hp=100, current_stats=dict(ctx["unit"].current_stats),
        stat_boosts=ctx["unit"].stat_boosts, status_effects=[], states=[],
        is_fainted=False, can_move=True, move_pp=[10], flags={},
    )
    # A fainted (but not-yet-removed) ally at (3,3) -- skipped since this move
    # has no revive effect (line ~6827-6828).
    fainted_ally = models.GameUnit(
        game_id=ctx["game"].id, unit_id=ctx["unit"].unit_id, user_id=http_user.id,
        starting_x=3, starting_y=3, current_x=3, current_y=3, level=50,
        current_hp=0, current_stats=dict(ctx["unit"].current_stats),
        stat_boosts=ctx["unit"].stat_boosts, status_effects=[], states=[],
        is_fainted=False, can_move=True, move_pp=[10], flags={},
    )
    db.add_all([known_ally, fainted_ally])
    db.commit()

    resp = client.post(
        "/games/exec-allytiles/execute_move",
        json={
            "unit_id": ctx["unit"].id,
            "move_id": ally_move.id,
            "target_ids": [known_ally.id],
            "effect_tiles": [[2, 2], [3, 3]],
        },
    )
    assert resp.status_code == 200


def test_execute_move_all_targeting_uses_affected_tiles_and_skips_fainted(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="exec-alltargets")
    all_move = models.Move(
        name="Field Blast", type="Normal", category="Status", power=None,
        accuracy=None, pp=10, effects=[], range="ranged", targeting="all",
    )
    db.add(all_move)
    db.commit()
    _equip_extra_move(db, ctx, all_move)

    fainted_unit = models.GameUnit(
        game_id=ctx["game"].id, unit_id=ctx["unit"].unit_id, user_id=ctx["opponent"].id,
        starting_x=0, starting_y=0, current_x=0, current_y=0, level=50,
        current_hp=0, current_stats=dict(ctx["unit"].current_stats),
        stat_boosts=ctx["unit"].stat_boosts, status_effects=[], states=[],
        is_fainted=False, can_move=True, move_pp=[10], flags={},
    )
    db.add(fainted_unit)
    db.commit()

    tile_set = {
        (ctx["opponent_unit"].current_x, ctx["opponent_unit"].current_y),
        (0, 0),
    }
    monkeypatch.setattr(games_module, "get_move_affected_tiles", lambda *a, **k: list(tile_set))

    resp = client.post(
        "/games/exec-alltargets/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": all_move.id, "target_ids": []},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# execute_move: top-of-function guard clauses (payload, encore, taunt/torment)
# ---------------------------------------------------------------------------


def test_execute_move_bad_effect_tile_entries_are_skipped(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-badtiles")
    resp = client.post(
        "/games/exec-badtiles/execute_move",
        json={
            "unit_id": ctx["unit"].id,
            "move_id": ctx["move"].id,
            "target_ids": [ctx["opponent_unit"].id],
            "effect_tiles": [["bad", "tile"], [1, 1]],
        },
    )
    assert resp.status_code == 200


def test_execute_move_top_guard_clauses(client, db, http_user, monkeypatch):
    resp = client.post("/games/no-such-link/execute_move", json={"unit_id": 1, "move_id": 1})
    assert resp.status_code == 404

    ctx = _create_battle_game(db, http_user, link="exec-notprog", preparation=True)
    resp = client.post(
        "/games/exec-notprog/execute_move", json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game not in progress"

    ctx2 = _create_battle_game(db, http_user, link="exec-completed")
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], True))
    resp = client.post(
        "/games/exec-completed/execute_move", json={"unit_id": ctx2["unit"].id, "move_id": ctx2["move"].id}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game completed"


def test_execute_move_invalid_state_forced(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="exec-invalidstate")
    monkeypatch.setattr(games_module, "reconcile_playable_players", lambda *a, **k: ([], [], False))
    resp = client.post(
        "/games/exec-invalidstate/execute_move", json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid game state"


def test_execute_move_unit_not_found(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-unitnotfound")
    resp = client.post(
        "/games/exec-unitnotfound/execute_move", json={"unit_id": 999999, "move_id": ctx["move"].id}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unit not found"


def test_execute_move_move_not_found(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-movenotfound")
    resp = client.post(
        "/games/exec-movenotfound/execute_move", json={"unit_id": ctx["unit"].id, "move_id": 999999}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Move not found"


def test_execute_move_encore_required_move_id_parse_exception(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-encorebad1")
    ctx["unit"].states = ["encore", 2, "not-an-int"]
    db.add(ctx["unit"])
    db.commit()
    # required_move_id parse fails -> None -> encore doesn't block -> proceeds normally.
    resp = client.post(
        "/games/exec-encorebad1/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200


def test_execute_move_encore_outer_exception_swallowed(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-encorebad2")
    ctx["unit"].states = ["encore", "not-an-int", ctx["move"].id]
    db.add(ctx["unit"])
    db.commit()
    resp = client.post(
        "/games/exec-encorebad2/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200


def test_execute_move_torment_skips_non_dict_and_wrong_event_log_entries(client, db, http_user):
    ctx = _create_battle_game(db, http_user, link="exec-tormentlog")
    ctx["unit"].states = ["torment", 2]
    db.add(ctx["unit"])
    ctx["state"].replay_log = [
        "not-a-dict",
        {"event": "unit_moved", "message": f"{get_unit_display_name(ctx['unit'], db)} used {ctx['move'].name}"},
    ]
    db.add(ctx["state"])
    db.commit()
    resp = client.post(
        "/games/exec-tormentlog/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200


def test_execute_move_taunt_torment_exception_swallowed(client, db, http_user, monkeypatch):
    ctx = _create_battle_game(db, http_user, link="exec-tauntexc")
    real_normalize_states = games_module.normalize_states
    call_state = {"n": 0}

    def fake_normalize_states(*a, **k):
        call_state["n"] += 1
        if call_state["n"] == 1:
            raise RuntimeError("boom")
        return real_normalize_states(*a, **k)

    monkeypatch.setattr(games_module, "normalize_states", fake_normalize_states)
    resp = client.post(
        "/games/exec-tauntexc/execute_move",
        json={"unit_id": ctx["unit"].id, "move_id": ctx["move"].id, "target_ids": [ctx["opponent_unit"].id]},
    )
    assert resp.status_code == 200


def test_weather_and_hazard_position_helper_edge_branches():
    # get_weather_id_at_position: row not list / x >= len -> 0.
    assert games_module.get_weather_id_at_position([None], 0, 0) == 0
    assert games_module.get_weather_id_at_position([["bad"]], 0, 0) == 0
    # get_hazard_entries_at_position: row not list / x >= len -> [].
    assert games_module.get_hazard_entries_at_position([None], 0, 0) == []
    # weather_condition_matches: unmatched condition string -> False.
    assert games_module.weather_condition_matches(0, "not_a_real_weather") is False
