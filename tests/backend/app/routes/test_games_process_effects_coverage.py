"""Comprehensive coverage tests for process_move_effects and end-of-round helpers.

These tests exercise as many effect-token branches of
``app.routes.games.process_move_effects`` as practical, plus the end-of-round
weather/stump/hazard helpers and a handful of supporting pure-function
helpers (validate_move_execution, resolve_power_multiplier, etc.).
"""

import itertools

import app.db.models as models
from app.routes.games import (
    FIELD_EFFECT_TO_ID,
    FIELD_HAZARD_TO_ID,
    TERRAIN_TO_ID,
    WEATHER_TO_ID,
    apply_confusion_self_damage,
    apply_end_of_round_entry_hazard_effects,
    apply_end_of_round_stump_tile_effects,
    apply_end_of_round_weather_damage,
    apply_stat_change,
    default_stat_boosts,
    get_stat_stage,
    get_move_hit_count,
    get_unit_flags,
    matches_effect_condition,
    normalize_status_effects,
    process_move_effects,
    resolve_move_accuracy,
    resolve_power_multiplier,
    resolve_shell_side_arm_mode,
    set_unit_flags,
    validate_move_execution,
)

_species_counter = itertools.count(920000)
_link_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Local fixtures / builders
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


def _make_map(db, creator_id, *, width=3, height=3, special_tiles=None):
    tile_data = {"movement_cost": [[1] * width for _ in range(height)]}
    if special_tiles is not None:
        tile_data["special_tiles"] = special_tiles
    map_obj = models.Map(
        name=f"Coverage Map {next(_link_counter)}",
        creator_id=creator_id,
        is_official=True,
        width=width,
        height=height,
        tileset_names=["grass"],
        tile_data=tile_data,
        allowed_modes=["Conquest"],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.commit()
    return map_obj


def _make_game(db, map_obj, user_ids):
    game = models.Game(
        game_name=f"Coverage Game {next(_link_counter)}",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=max(2, len(user_ids)),
        gamemode="Conquest",
        is_private=False,
        host_id=user_ids[0],
        link=f"cov-link-{next(_link_counter)}",
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


# ---------------------------------------------------------------------------
# process_move_effects: weather / terrain / field hazard tile tokens
# ---------------------------------------------------------------------------


def test_weather_terrain_field_hazard_tokens(db):
    user = _make_user(db, "wt-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    map_state = _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "Wt Mon")
    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)

    move = models.Move(
        name="Field Combo",
        type="Normal",
        category="Status",
        effects=[
            "weather:sun",
            "weather:rain",
            "weather:sandstorm",
            "weather:hail",
            "terrain:electric",
            "terrain:psychic",
            "terrain:grassy",
            "terrain:misty",
            "field_hazard:spikes",
            "field_hazard:toxic_spikes",
            "field_hazard:stealth_rock",
            "field_hazard:sticky_web",
            "weather:unknown_weather",
            "field_hazard:unknown_hazard",
            "terrain:unknown_terrain",
        ],
    )

    process_move_effects(
        move,
        attacker,
        [],
        current_turn=0,
        db=db,
        weather_tiles=map_state.weather_tiles,
        terrain_tiles=map_state.terrain_effect_tiles,
        field_effect_tiles=map_state.field_effect_tiles,
        affected_tiles_override=[(1, 1)],
        game=game,
        game_state=state,
    )
    db.commit()
    db.refresh(map_state)

    assert map_state.weather_tiles[1][1] == WEATHER_TO_ID["hail"]
    assert map_state.terrain_effect_tiles[1][1][0] == TERRAIN_TO_ID["misty"]
    hazard_ids = {entry[0] for entry in map_state.hazard_tiles[1][1]}
    assert hazard_ids == {
        FIELD_HAZARD_TO_ID["spikes"],
        FIELD_HAZARD_TO_ID["toxic_spikes"],
        FIELD_HAZARD_TO_ID["stealth_rock"],
        FIELD_HAZARD_TO_ID["sticky_web"],
    }


# ---------------------------------------------------------------------------
# process_move_effects: field clear/tailwind/gravity tokens
# ---------------------------------------------------------------------------


def test_field_clear_hazards_substitutes_tailwind_gravity(db):
    user = _make_user(db, "field2-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    map_state = _make_map_state(db, game, map_obj)

    # Pre-seed hazards on both the override tile and the attacker's own tile.
    # NOTE: hazard_tiles/field_effect_tiles are plain nested lists inside a
    # MutableList JSON column; mutating a nested cell in place is not tracked
    # by SQLAlchemy, so we must reassign the whole list for the change to
    # actually persist across the commit()/expire_on_commit cycle.
    seeded_hazards = [[[] for _ in range(3)] for _ in range(3)]
    seeded_hazards[1][1] = [[FIELD_HAZARD_TO_ID["spikes"], 5]]
    seeded_hazards[0][0] = [[FIELD_HAZARD_TO_ID["stealth_rock"], 5]]
    map_state.hazard_tiles = seeded_hazards
    db.add(map_state)
    db.commit()

    unit_def = _make_unit_def(db, "Clear Mon")
    attacker = _make_game_unit(db, unit_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id)
    sub_unit = _make_game_unit(
        db,
        unit_def,
        x=1,
        y=1,
        hp=50,
        max_hp=50,
        game=game,
        user_id=user.id,
        states=["substitute", 9999],
    )

    move = models.Move(
        name="Field Utility",
        type="Normal",
        category="Status",
        effects=[
            "field:clear_hazards",
            "field:clear_substitutes",
            "self:clear_hazards",
            "field:tailwind",
            "field:gravity",
        ],
    )

    process_move_effects(
        move,
        attacker,
        [],
        current_turn=0,
        db=db,
        weather_tiles=map_state.weather_tiles,
        terrain_tiles=map_state.terrain_effect_tiles,
        field_effect_tiles=map_state.field_effect_tiles,
        affected_tiles_override=[(1, 1)],
        game=game,
        game_state=state,
    )

    # These two fields are only mutated via nested (untracked) list writes by
    # the production code, so we must assert on them *before* the next
    # commit() (which expires and would silently reload the stale, still
    # -persisted values from the DB and mask the in-memory mutation).
    assert map_state.hazard_tiles[1][1] == []
    assert map_state.hazard_tiles[0][0] == []
    assert map_state.field_effect_tiles[1][1] == FIELD_EFFECT_TO_ID["gravity"]

    db.commit()
    db.refresh(sub_unit)
    db.refresh(attacker)

    assert sub_unit.states == []
    assert attacker.states == ["tailwind", 5]

    # Repeating field:clear_hazards with no map_state present is a no-op (continue branch).
    other_user = _make_user(db, "field2-user-b")
    other_map = _make_map(db, other_user.id)
    other_game = _make_game(db, other_map, [other_user.id])
    other_attacker = _make_game_unit(
        db, unit_def, x=0, y=0, hp=50, max_hp=50, game=other_game, user_id=other_user.id
    )
    process_move_effects(
        move,
        other_attacker,
        [],
        current_turn=0,
        db=db,
        weather_tiles=None,
        terrain_tiles=None,
        field_effect_tiles=None,
        affected_tiles_override=[(0, 0)],
        game=other_game,
        game_state=None,
    )


# ---------------------------------------------------------------------------
# process_move_effects: held item / conditional stat / hazard / crit tokens
# ---------------------------------------------------------------------------


def test_item_and_conditional_stat_tokens(db):
    user = _make_user(db, "item-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    map_state = _make_map_state(db, game, map_obj)
    # Reassign the whole grids (rather than mutating a nested cell in place)
    # so the change actually survives the commit()/expire_on_commit cycle.
    seeded_weather = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    seeded_weather[1][1] = WEATHER_TO_ID["sun"]
    map_state.weather_tiles = seeded_weather
    seeded_terrain = [[[0, 0] for _ in range(3)] for _ in range(3)]
    seeded_terrain[1][1] = [TERRAIN_TO_ID["electric"], 5]
    map_state.terrain_effect_tiles = seeded_terrain
    db.add(map_state)
    db.commit()

    attacker_def = _make_unit_def(db, "Item Attacker", types=["Fire"])
    target_def = _make_unit_def(db, "Item Target Fire", types=["Fire"])
    target2_def = _make_unit_def(db, "Item Target Normal", types=["Normal"])

    attacker = _make_game_unit(
        db,
        attacker_def,
        x=1,
        y=1,
        hp=60,
        max_hp=60,
        game=game,
        user_id=user.id,
        flags={"held_item": "oran_berry"},
    )
    target1 = _make_game_unit(
        db,
        target_def,
        x=0,
        y=0,
        hp=60,
        max_hp=60,
        game=game,
        user_id=user.id,
        flags={"held_item": "oran_berry"},
    )
    target2 = _make_game_unit(
        db,
        target2_def,
        x=2,
        y=2,
        hp=60,
        max_hp=60,
        game=game,
        user_id=user.id,
        flags={"held_item": "leftovers"},
    )

    move = models.Move(
        name="Item Combo",
        type="Normal",
        category="Status",
        effects=[
            "self:consume_berry",
            "target:consume_berry",
            "target:remove_held_item",
            "target:field_hazard:spikes",
            "self:raise_stat:condition:weather:sun:attack:2",
            "self:raise_stat:condition:terrain:electric:sp_attack:1",
            "target:raise_stat:condition:is_type:fire:attack:1",
            "target:lower_stat:condition:not_type:flying:speed:1",
            "self:high_crit_ratio",
        ],
    )

    process_move_effects(
        move,
        attacker,
        [target1, target2],
        current_turn=0,
        db=db,
        weather_tiles=map_state.weather_tiles,
        terrain_tiles=map_state.terrain_effect_tiles,
        field_effect_tiles=map_state.field_effect_tiles,
        affected_tiles_override=[(1, 1)],
        game=game,
        game_state=state,
    )
    db.commit()
    db.refresh(map_state)
    db.refresh(attacker)
    db.refresh(target1)
    db.refresh(target2)

    assert get_unit_flags(attacker).get("held_item") is None
    assert get_unit_flags(target1).get("held_item") is None
    assert get_unit_flags(target2).get("held_item") is None
    assert map_state.hazard_tiles[0][0] != []
    assert map_state.hazard_tiles[2][2] != []
    assert get_stat_stage(attacker.stat_boosts, "attack") == 2
    assert get_stat_stage(attacker.stat_boosts, "sp_attack") == 1
    assert get_stat_stage(attacker.stat_boosts, "crit") == 1
    assert get_stat_stage(target1.stat_boosts, "attack") == 1
    assert get_stat_stage(target1.stat_boosts, "speed") == -1
    assert get_stat_stage(target2.stat_boosts, "speed") == -1
    assert get_stat_stage(target2.stat_boosts, "attack") == 0


# ---------------------------------------------------------------------------
# process_move_effects: status / safeguard / apply_state tokens
# ---------------------------------------------------------------------------


def test_status_safeguard_and_apply_state_tokens(db):
    user = _make_user(db, "status-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)

    normal_def = _make_unit_def(db, "Status Normal", types=["Normal"])
    poison_def = _make_unit_def(db, "Status Poison", types=["Poison"])
    ghost_def = _make_unit_def(db, "Status Ghost", types=["Ghost"])

    attacker = _make_game_unit(db, normal_def, x=1, y=1, hp=50, max_hp=50, game=game, user_id=user.id)
    target_plain = _make_game_unit(db, normal_def, x=0, y=0, hp=50, max_hp=50, game=game, user_id=user.id)
    target_safe = _make_game_unit(
        db, normal_def, x=0, y=1, hp=50, max_hp=50, game=game, user_id=user.id, states=["safeguard", 5]
    )
    target_poison = _make_game_unit(db, poison_def, x=1, y=0, hp=50, max_hp=50, game=game, user_id=user.id)
    target_ghost = _make_game_unit(db, ghost_def, x=2, y=0, hp=50, max_hp=50, game=game, user_id=user.id)

    move = models.Move(
        name="Status Combo",
        type="Normal",
        category="Status",
        effects=[
            "target:status:paralysis",
            "target:status:condition:type:poison:status:poison",
            "self:safeguard",
            "target:apply_state:condition:type:ghost:confusion",
            "target:apply_state:flinch",
        ],
    )

    process_move_effects(
        move,
        attacker,
        [target_plain, target_safe, target_poison, target_ghost],
        current_turn=0,
        db=db,
        weather_tiles=None,
        terrain_tiles=None,
        field_effect_tiles=None,
        affected_tiles_override=[(1, 1)],
        game=game,
        game_state=state,
    )
    db.commit()
    for unit in (attacker, target_plain, target_safe, target_poison, target_ghost):
        db.refresh(unit)

    assert normalize_status_effects(target_plain.status_effects)[0] == "paralysis"
    assert target_safe.status_effects == []
    assert attacker.states[0] == "safeguard"
    assert target_ghost.states[0] == "confusion"
    assert target_plain.states[0] == "flinch"


def test_break_screens_token(db):
    user = _make_user(db, "break-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    state = _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)
    unit_def = _make_unit_def(db, "Break Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, game=game, user_id=user.id)
    ally_screened = _make_game_unit(
        db, unit_def, x=2, y=2, hp=40, max_hp=40, game=game, user_id=user.id, states=["reflect", 5]
    )

    move = models.Move(name="Break Screens", type="Normal", category="Status", effects=["break_screens"])

    process_move_effects(
        move,
        attacker,
        [target],
        current_turn=0,
        db=db,
        weather_tiles=None,
        terrain_tiles=None,
        field_effect_tiles=None,
        affected_tiles_override=[(1, 1)],
        game=game,
        game_state=state,
    )
    db.commit()
    db.refresh(ally_screened)
    assert ally_screened.states == []


# ---------------------------------------------------------------------------
# process_move_effects: copy_ability / defog
# ---------------------------------------------------------------------------


def test_copy_ability_and_defog_tokens(db):
    user = _make_user(db, "ability-user")
    other_user = _make_user(db, "ability-user2")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id, other_user.id])
    state = _make_state(db, game, [user.id, other_user.id])
    _make_map_state(db, game, map_obj)

    ability = models.Ability(name="Levitate", slug="levitate-cov", generation=3)
    db.add(ability)
    db.commit()

    unit_def = _make_unit_def(db, "Ability Mon")

    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40, game=game, user_id=user.id)
    source_unit = _make_game_unit(
        db,
        unit_def,
        x=0,
        y=0,
        hp=40,
        max_hp=40,
        game=game,
        user_id=other_user.id,
        flags={"ability_id": ability.id},
    )
    screened_ally = _make_game_unit(
        db,
        unit_def,
        x=2,
        y=2,
        hp=40,
        max_hp=40,
        game=game,
        user_id=other_user.id,
        states=["reflect", 5],
    )

    move = models.Move(
        name="Ability Combo",
        type="Normal",
        category="Status",
        effects=["self:copy_ability:target", "ally:copy_ability:target", "target:defog"],
    )

    process_move_effects(
        move,
        attacker,
        [source_unit],
        current_turn=0,
        db=db,
        weather_tiles=None,
        terrain_tiles=None,
        field_effect_tiles=None,
        affected_tiles_override=[(1, 1)],
        game=game,
        game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(screened_ally)

    assert get_unit_flags(attacker).get("ability_id") == ability.id
    assert screened_ally.states == []


# ---------------------------------------------------------------------------
# process_move_effects: heal / cure_status / reset_stats / give_cash /
# revive / instant_ko
# ---------------------------------------------------------------------------


def test_heal_cure_reset_cash_revive_ko_tokens(db):
    user = _make_user(db, "combo-user")
    cash_user = _make_user(db, "cash-user")
    other_user = _make_user(db, "other-user")

    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id, cash_user.id, other_user.id])
    state = _make_state(db, game, [user.id, cash_user.id, other_user.id])
    map_state = _make_map_state(db, game, map_obj)
    seeded_weather = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    seeded_weather[1][1] = WEATHER_TO_ID["sun"]
    map_state.weather_tiles = seeded_weather
    db.add(map_state)
    db.commit()

    db.add(models.GamePlayer(game_id=game.id, player_id=cash_user.id, cash_remaining=100, game_units=[]))
    db.commit()

    unit_def = _make_unit_def(db, "Combo Mon")

    attacker = _make_game_unit(
        db,
        unit_def,
        x=1,
        y=1,
        hp=10,
        max_hp=50,
        game=game,
        user_id=user.id,
        stat_boosts={
            "attack": [{"magnitude": 2, "expires_turn": 4}],
            "defense": [],
            "sp_attack": [],
            "sp_defense": [],
            "speed": [],
            "accuracy": [],
            "evasion": [],
            "crit": [],
        },
    )
    target_cured = _make_game_unit(
        db,
        unit_def,
        x=0,
        y=0,
        hp=50,
        max_hp=50,
        game=game,
        user_id=other_user.id,
        status_effects=["burn", 3],
    )
    target_cash = _make_game_unit(db, unit_def, x=2, y=0, hp=50, max_hp=50, game=game, user_id=cash_user.id)
    target_fainted = _make_game_unit(
        db,
        unit_def,
        x=0,
        y=2,
        hp=0,
        max_hp=50,
        game=game,
        user_id=user.id,
        is_fainted=True,
    )
    target_ko = _make_game_unit(db, unit_def, x=2, y=2, hp=50, max_hp=50, game=game, user_id=other_user.id)

    move = models.Move(
        name="Support Combo",
        type="Normal",
        category="Status",
        effects=[
            "self:heal:2",
            "self:heal:condition:weather:sun:3",
            "target:cure_status:all",
            "self:reset_stats",
            "target:give_cash:50",
            "target:instant_ko",
            "target:revive:2",
        ],
    )

    process_move_effects(
        move,
        attacker,
        [target_cured, target_cash, target_fainted, target_ko],
        current_turn=0,
        db=db,
        weather_tiles=map_state.weather_tiles,
        terrain_tiles=None,
        field_effect_tiles=None,
        affected_tiles_override=[(1, 1)],
        game=game,
        game_state=state,
    )
    db.commit()
    db.refresh(attacker)
    db.refresh(target_cured)
    db.refresh(target_fainted)
    db.refresh(target_ko)

    assert attacker.current_hp > 10
    assert get_stat_stage(attacker.stat_boosts, "attack") == 0
    assert target_cured.status_effects == []

    player_state = db.query(models.GamePlayer).filter_by(game_id=game.id, player_id=cash_user.id).first()
    assert player_state.cash_remaining == 150

    assert target_fainted.is_fainted is False
    assert target_fainted.current_hp > 0
    assert target_ko.current_hp == 0


# ---------------------------------------------------------------------------
# End-of-round helpers
# ---------------------------------------------------------------------------


def test_apply_end_of_round_weather_damage_all_branches(db):
    user = _make_user(db, "eor-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    map_state = _make_map_state(db, game, map_obj)
    map_state.weather_tiles = [
        [WEATHER_TO_ID["sandstorm"], WEATHER_TO_ID["hail"], 0],
        [0, 0, 0],
        [0, 0, 0],
    ]
    db.add(map_state)
    db.commit()

    fire_def = _make_unit_def(db, "EOR Fire", types=["Fire"])
    rock_def = _make_unit_def(db, "EOR Rock", types=["Rock"])
    water_def = _make_unit_def(db, "EOR Water", types=["Water"])
    ice_def = _make_unit_def(db, "EOR Ice", types=["Ice"])
    normal_def = _make_unit_def(db, "EOR Normal", types=["Normal"])
    steel_def = _make_unit_def(db, "EOR Steel", types=["Steel"])

    fire_unit = _make_game_unit(db, fire_def, x=0, y=0, hp=80, max_hp=80, game=game, user_id=user.id)
    rock_unit = _make_game_unit(db, rock_def, x=0, y=0, hp=80, max_hp=80, game=game, user_id=user.id)
    water_unit = _make_game_unit(db, water_def, x=1, y=0, hp=80, max_hp=80, game=game, user_id=user.id)
    ice_unit = _make_game_unit(db, ice_def, x=1, y=0, hp=80, max_hp=80, game=game, user_id=user.id)

    aqua_unit = _make_game_unit(
        db, normal_def, x=2, y=2, hp=10, max_hp=80, game=game, user_id=user.id, states=["aqua_ring", 5]
    )
    ingrain_unit = _make_game_unit(
        db, normal_def, x=2, y=2, hp=10, max_hp=80, game=game, user_id=user.id, states=["ingrain", 5]
    )
    aqua_heal_blocked = _make_game_unit(
        db,
        normal_def,
        x=2,
        y=2,
        hp=10,
        max_hp=80,
        game=game,
        user_id=user.id,
        states=["aqua_ring", 5],
    )
    cursed_unit = _make_game_unit(
        db, normal_def, x=2, y=2, hp=80, max_hp=80, game=game, user_id=user.id, states=["cursed", 5]
    )
    nightmare_asleep = _make_game_unit(
        db,
        normal_def,
        x=2,
        y=2,
        hp=80,
        max_hp=80,
        game=game,
        user_id=user.id,
        states=["nightmare", 9999],
        status_effects=["sleep", 3],
    )
    nightmare_awake = _make_game_unit(
        db, normal_def, x=2, y=2, hp=80, max_hp=80, game=game, user_id=user.id, states=["nightmare", 9999]
    )
    salt_water_unit = _make_game_unit(
        db, water_def, x=2, y=2, hp=80, max_hp=80, game=game, user_id=user.id, states=["salt_cure", 5]
    )
    salt_steel_unit = _make_game_unit(
        db, steel_def, x=2, y=2, hp=80, max_hp=80, game=game, user_id=user.id, states=["salt_cure", 5]
    )
    salt_normal_unit = _make_game_unit(
        db, normal_def, x=2, y=2, hp=80, max_hp=80, game=game, user_id=user.id, states=["salt_cure", 5]
    )

    # Manually force heal-block on one aqua-ring unit to hit the Heal Block skip branch.
    aqua_heal_blocked.states = ["aqua_ring", 5]
    db.add(aqua_heal_blocked)
    db.commit()

    modified = apply_end_of_round_weather_damage(game.id, db)
    db.commit()
    for unit in (
        fire_unit,
        rock_unit,
        water_unit,
        ice_unit,
        aqua_unit,
        ingrain_unit,
        cursed_unit,
        nightmare_asleep,
        nightmare_awake,
        salt_water_unit,
        salt_steel_unit,
        salt_normal_unit,
    ):
        db.refresh(unit)

    assert fire_unit.current_hp < 80
    assert rock_unit.current_hp == 80
    assert water_unit.current_hp < 80
    assert ice_unit.current_hp == 80
    assert aqua_unit.current_hp > 10
    assert ingrain_unit.current_hp > 10
    assert cursed_unit.current_hp < 80
    assert nightmare_asleep.current_hp < 80
    assert nightmare_awake.current_hp == 80
    assert salt_water_unit.current_hp < salt_normal_unit.current_hp
    assert salt_steel_unit.current_hp == salt_water_unit.current_hp
    assert modified


def test_apply_end_of_round_stump_tile_effects(db):
    user = _make_user(db, "stump-user")
    special_tiles = [
        ["stump", "", ""],
        ["", "", ""],
        ["", "", ""],
    ]
    map_obj = _make_map(db, user.id, special_tiles=special_tiles)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    _make_map_state(db, game, map_obj)

    grass_def = _make_unit_def(db, "Stump Grass", types=["Grass"])
    flying_grass_def = _make_unit_def(db, "Stump Flying Grass", types=["Grass", "Flying"])

    healer = _make_game_unit(db, grass_def, x=0, y=0, hp=10, max_hp=80, game=game, user_id=user.id)
    blocked = _make_game_unit(
        db, grass_def, x=0, y=0, hp=80, max_hp=80, game=game, user_id=user.id, states=["heal_block", 5]
    )
    flyer = _make_game_unit(db, flying_grass_def, x=0, y=0, hp=10, max_hp=80, game=game, user_id=user.id)
    off_tile = _make_game_unit(db, grass_def, x=1, y=1, hp=10, max_hp=80, game=game, user_id=user.id)

    modified = apply_end_of_round_stump_tile_effects(game.id, db)
    db.commit()
    db.refresh(healer)
    db.refresh(blocked)
    db.refresh(flyer)
    db.refresh(off_tile)

    assert healer.current_hp > 10
    assert blocked.current_hp == 80
    assert flyer.current_hp == 10
    assert off_tile.current_hp == 10
    assert healer.id in modified


def test_apply_end_of_round_entry_hazard_effects(db):
    user = _make_user(db, "hazard-user")
    map_obj = _make_map(db, user.id)
    game = _make_game(db, map_obj, [user.id])
    _make_state(db, game, [user.id])
    map_state = _make_map_state(db, game, map_obj)
    map_state.hazard_tiles = [
        [[[1, 5]], [[1, 5], [1, 5]], [[1, 5], [1, 5], [1, 5]]],
        [[[3, 5]], [[2, 5]], [[2, 5], [2, 5]]],
        [[[4, 5]], [], []],
    ]
    db.add(map_state)
    db.commit()

    normal_def = _make_unit_def(db, "Hazard Normal", types=["Normal"])
    flying_def = _make_unit_def(db, "Hazard Flying", types=["Flying"])
    grass_def = _make_unit_def(db, "Hazard Grass", types=["Grass"])
    poison_def = _make_unit_def(db, "Hazard Poison", types=["Poison"])

    spikes1 = _make_game_unit(db, normal_def, x=0, y=0, hp=80, max_hp=80, game=game, user_id=user.id)
    spikes2 = _make_game_unit(db, normal_def, x=1, y=0, hp=80, max_hp=80, game=game, user_id=user.id)
    spikes3 = _make_game_unit(db, normal_def, x=2, y=0, hp=80, max_hp=80, game=game, user_id=user.id)
    flying_on_spikes = _make_game_unit(db, flying_def, x=0, y=0, hp=80, max_hp=80, game=game, user_id=user.id)
    rock_target = _make_game_unit(db, grass_def, x=0, y=1, hp=80, max_hp=80, game=game, user_id=user.id)
    toxic1 = _make_game_unit(db, normal_def, x=1, y=1, hp=80, max_hp=80, game=game, user_id=user.id)
    toxic2 = _make_game_unit(db, poison_def, x=2, y=1, hp=80, max_hp=80, game=game, user_id=user.id)
    web_unit = _make_game_unit(db, normal_def, x=0, y=2, hp=80, max_hp=80, game=game, user_id=user.id)

    modified = apply_end_of_round_entry_hazard_effects(game.id, current_turn=0, db=db)
    db.commit()
    for unit in (spikes1, spikes2, spikes3, flying_on_spikes, rock_target, toxic1, toxic2, web_unit):
        db.refresh(unit)

    assert spikes1.current_hp == 80 - max(1, 80 // 8)
    assert spikes2.current_hp == 80 - max(1, 80 // 6)
    assert spikes3.current_hp == 80 - max(1, 80 // 4)
    assert flying_on_spikes.current_hp == 80
    assert rock_target.current_hp < 80
    assert toxic1.status_effects[0] == "poison"
    assert toxic2.status_effects == []
    assert get_stat_stage(web_unit.stat_boosts, "speed") == -1
    assert modified


# ---------------------------------------------------------------------------
# Supporting helper-function coverage
# ---------------------------------------------------------------------------


def test_validate_move_execution_branches(db):
    unit_def = _make_unit_def(db, "Validate Mon", types=["Fire"])
    attacker = _make_game_unit(db, unit_def, x=1, y=1, hp=40, max_hp=40)
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)

    berry_move = models.Move(name="Berry Move", type="Normal", category="Status", effects=["requires:held_item:berry"])
    assert validate_move_execution(berry_move, attacker, [target], None, db) == "It doesn't have a Berry to eat"

    set_unit_flags(attacker, {"held_item": "oran_berry"}, db)
    db.commit()
    assert validate_move_execution(berry_move, attacker, [target], None, db) is None

    item_move = models.Move(name="Item Move", type="Normal", category="Status", effects=["requires:target:held_item"])
    assert (
        validate_move_execution(item_move, attacker, [target], None, db)
        == "The move failed because the target has no item"
    )
    assert validate_move_execution(item_move, attacker, [], None, db) == "The move failed"

    terrain_move = models.Move(
        name="Terrain Move", type="Normal", category="Status", effects=["requires:target_terrain:active"]
    )
    empty_terrain = [[[0, 0], [0, 0]], [[0, 0], [0, 0]]]
    assert validate_move_execution(terrain_move, attacker, [target], empty_terrain, db) == "But it failed"
    assert validate_move_execution(terrain_move, attacker, [], empty_terrain, db) == "But it failed"
    active_terrain = [[[1, 5], [0, 0]], [[0, 0], [0, 0]]]
    assert validate_move_execution(terrain_move, attacker, [target], active_terrain, db) is None

    type_move = models.Move(name="Type Move", type="Normal", category="Status", effects=["requires:type:water"])
    assert validate_move_execution(type_move, attacker, [target], None, db) == "But it failed"

    last_attacker_move = models.Move(
        name="Last Attacker Move", type="Normal", category="Status", effects=["requires:last_damage_attacker"]
    )
    assert validate_move_execution(last_attacker_move, attacker, [target], None, db) == "But it failed"

    set_unit_flags(attacker, {"last_damage_attacker_id": 999999}, db)
    db.commit()
    assert validate_move_execution(last_attacker_move, attacker, [target], None, db) == "But it failed"

    dead_attacker = _make_game_unit(db, unit_def, x=2, y=2, hp=0, max_hp=40)
    set_unit_flags(attacker, {"last_damage_attacker_id": dead_attacker.id}, db)
    db.commit()
    assert validate_move_execution(last_attacker_move, attacker, [target], None, db) == "But it failed"

    alive_attacker = _make_game_unit(db, unit_def, x=2, y=1, hp=40, max_hp=40)
    set_unit_flags(attacker, {"last_damage_attacker_id": alive_attacker.id}, db)
    db.commit()
    assert validate_move_execution(last_attacker_move, attacker, [target], None, db) is None

    half_hp_move = models.Move(name="Half HP Move", type="Normal", category="Status", effects=["fail_if:below_half_hp"])
    attacker.current_hp = 5
    db.commit()
    assert validate_move_execution(half_hp_move, attacker, [target], None, db) == "But it failed"
    attacker.current_hp = 40
    db.commit()
    assert validate_move_execution(half_hp_move, attacker, [target], None, db) is None

    max_stats_move = models.Move(
        name="Max Stats Move", type="Normal", category="Status", effects=["fail_if:stats_at_max:attack,defense"]
    )
    attacker.stat_boosts = {
        "attack": [{"magnitude": 6, "expires_turn": 4}],
        "defense": [{"magnitude": 6, "expires_turn": 4}],
    }
    db.commit()
    assert validate_move_execution(max_stats_move, attacker, [target], None, db) == "But it failed"
    attacker.stat_boosts = default_stat_boosts()
    db.commit()
    assert validate_move_execution(max_stats_move, attacker, [target], None, db) is None

    revive_move = models.Move(name="Revive Move", type="Normal", category="Status", effects=["target:revive:2"])
    attacker.states = ["heal_block", 5]
    db.commit()
    assert validate_move_execution(revive_move, attacker, [target], None, db) == "But it failed"
    attacker.states = []
    db.commit()
    assert validate_move_execution(revive_move, attacker, [target], None, db) is None


def test_resolve_power_multiplier_branches(db):
    fire_def = _make_unit_def(db, "Power Fire", types=["Fire"])
    grass_def = _make_unit_def(db, "Power Grass", types=["Grass"])
    attacker = _make_game_unit(db, fire_def, x=0, y=0, hp=40, max_hp=40)
    target = _make_game_unit(db, grass_def, x=0, y=0, hp=40, max_hp=40)

    terrain_tiles = [[[TERRAIN_TO_ID["electric"], 5]]]
    field_effect_tiles = [[FIELD_EFFECT_TO_ID["gravity"]]]
    weather_tiles = [[WEATHER_TO_ID["sun"]]]

    move = models.Move(
        name="Power Combo",
        type="Fire",
        category="Special",
        power=60,
        effects=[
            "conditional_power:terrain:electric:2",
            "conditional_power:target_terrain:electric:2",
            "conditional_power:field:gravity:1.5",
            "conditional_power:self:stat_lowered_since_turn:1.5",
            "conditional_power:target_status:burn:1.5",
            "conditional_power:target:has_status:1.5",
            "conditional_power:super_effective:1.5",
            "conditional_power:chance:100:2",
            "conditional_power:weather:sun:1.5",
            "not_conditional_power:ignored",
        ],
    )

    set_unit_flags(attacker, {"stat_stages_at_turn_start": {"attack": 1}}, db)
    attacker.stat_boosts = {"attack": [{"magnitude": -1, "expires_turn": 4}]}
    target.status_effects = ["burn", 3]
    db.commit()

    multiplier = resolve_power_multiplier(
        move, attacker, target, terrain_tiles, field_effect_tiles, db, weather_tiles=weather_tiles
    )
    assert multiplier > 1.0

    multiplier_no_target = resolve_power_multiplier(move, attacker, None, terrain_tiles, field_effect_tiles, db)
    assert multiplier_no_target > 1.0

    plain_move = models.Move(name="Plain", type="Normal", category="Physical", power=40, effects=[])
    assert resolve_power_multiplier(plain_move, attacker, target, None, None, db) == 1.0
    assert resolve_power_multiplier(None, attacker, target, None, None, db) == 1.0


def test_resolve_shell_side_arm_mode_branches(db):
    unit_def = _make_unit_def(db, "Shell Mon", types=["Poison"])
    attacker_physical = _make_game_unit(
        db, unit_def, x=0, y=0, hp=40, max_hp=40, current_stats_extra={"attack": 150, "sp_attack": 10}
    )
    attacker_special = _make_game_unit(
        db, unit_def, x=0, y=0, hp=40, max_hp=40, current_stats_extra={"attack": 10, "sp_attack": 150}
    )
    target = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)

    move = models.Move(name="Shell Side Arm", type="Poison", category="Special", power=90)

    is_special, makes_contact = resolve_shell_side_arm_mode(
        move,
        attacker_physical,
        target,
        terrain_tiles=None,
        weather_tiles=None,
        special_tiles=None,
        db=db,
        targets_multiplier=1.0,
    )
    assert is_special is False
    assert makes_contact is True

    is_special2, makes_contact2 = resolve_shell_side_arm_mode(
        move,
        attacker_special,
        target,
        terrain_tiles=None,
        weather_tiles=None,
        special_tiles=None,
        db=db,
        targets_multiplier=1.0,
    )
    assert is_special2 is True
    assert makes_contact2 is False


def test_matches_effect_condition_branches(db):
    ability = models.Ability(name="Cond Ability", slug="cond-ability", generation=1)
    db.add(ability)
    db.commit()

    unit_def = _make_unit_def(db, "Cond Mon", types=["Ghost"])
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40, flags={"ability_id": ability.id})

    assert matches_effect_condition(unit, "type", "ghost", db) is True
    assert matches_effect_condition(unit, "not_type", "ghost", db) is False
    assert matches_effect_condition(unit, "not_type", "fire", db) is True
    assert matches_effect_condition(unit, "has_ability", "cond ability", db) is True
    assert matches_effect_condition(unit, "not_has_ability", "cond ability", db) is False
    assert matches_effect_condition(unit, "unknown_condition", "x", db) is False
    assert matches_effect_condition(unit, "type", "", db) is False

    unit.states = ["gastro_acid", 3]
    db.commit()
    assert matches_effect_condition(unit, "has_ability", "cond ability", db) is False
    assert matches_effect_condition(unit, "not_has_ability", "cond ability", db) is True
    unit.states = []
    db.commit()

    unit.flags = {"stat_stages_at_turn_start": {}}
    unit.stat_boosts = {"attack": [{"magnitude": 1, "expires_turn": 4}]}
    db.commit()
    assert matches_effect_condition(unit, "stat_boosted", "x", db) is True
    assert matches_effect_condition(unit, "stat_raised_since_turn", "x", db) is True


def test_apply_stat_change_cancellation(db):
    unit_def = _make_unit_def(db, "Stat Mon")
    unit = _make_game_unit(db, unit_def, x=0, y=0, hp=40, max_hp=40)

    apply_stat_change(unit, "attack", 2, current_turn=0, db=db)
    assert get_stat_stage(unit.stat_boosts, "attack") == 2

    apply_stat_change(unit, "attack", -1, current_turn=0, db=db)
    assert get_stat_stage(unit.stat_boosts, "attack") == 1

    apply_stat_change(unit, "attack", -3, current_turn=0, db=db)
    assert get_stat_stage(unit.stat_boosts, "attack") == -2

    apply_stat_change(unit, "attack", 2, current_turn=0, db=db)
    assert get_stat_stage(unit.stat_boosts, "attack") == 0


def test_normalize_status_effects_variants():
    assert normalize_status_effects(None) == []
    assert normalize_status_effects(123) == []
    assert normalize_status_effects("burn") == ["burn", 1]
    assert normalize_status_effects(["poison", 3]) == ["poison", 3]
    assert normalize_status_effects(["badly_poison", 5, 2]) == ["badly_poisoned", 5, 2]
    assert normalize_status_effects({"status": "sleep", "expires_turn": 4}) == ["sleep", 4]
    assert normalize_status_effects(
        {"status": "badly_poisoned", "expires_turn": 5, "bad_poison_turn": 2}
    ) == ["badly_poisoned", 5, 2]
    assert normalize_status_effects(["invalid_status", 3]) == []
    assert normalize_status_effects([["burn", 2], "junk"]) == ["burn", 2]


def test_apply_confusion_self_damage(db):
    unit_def = _make_unit_def(db, "Confuse Mon")
    unit = _make_game_unit(
        db, unit_def, x=0, y=0, hp=40, max_hp=40, current_stats_extra={"attack": 100, "defense": 50}
    )

    damage = apply_confusion_self_damage(unit, db)
    assert damage > 0
    assert unit.current_hp == 40 - damage

    zero_hp_unit = _make_game_unit(db, unit_def, x=1, y=1, hp=0, max_hp=0, current_stats_extra={"hp": 0})
    assert apply_confusion_self_damage(zero_hp_unit, db) == 0


def test_get_move_hit_count_variants():
    dragon_darts = models.Move(name="Dragon Darts", type="Dragon", category="Physical", effects=["multi_hit:dragon_darts"])
    assert get_move_hit_count(dragon_darts, landed_target_count=1) == 2
    assert get_move_hit_count(dragon_darts, landed_target_count=2) == 1

    scaling = models.Move(name="Triple Axel", type="Ice", category="Physical", effects=["multi_hit:scaling:20,40,60"])
    assert get_move_hit_count(scaling) == 3

    variable = models.Move(name="Population Bomb", type="Normal", category="Physical", effects=["multi_hit:variable"])
    assert get_move_hit_count(variable) in {2, 3, 4, 5}

    party = models.Move(name="Party Move", type="Normal", category="Status", effects=["multi_hit:party"])
    assert get_move_hit_count(party) == 1

    fixed_range = models.Move(name="Fixed Range", type="Normal", category="Physical", effects=["multi_hit:2:5"])
    assert 2 <= get_move_hit_count(fixed_range) <= 5

    fixed_single = models.Move(name="Fixed Single", type="Normal", category="Physical", effects=["multi_hit:3"])
    assert get_move_hit_count(fixed_single) == 3

    invalid = models.Move(name="Invalid Multi", type="Normal", category="Physical", effects=["multi_hit:abc"])
    assert get_move_hit_count(invalid) == 1

    no_effects = models.Move(name="No Effects", type="Normal", category="Physical", effects=[])
    assert get_move_hit_count(no_effects) == 1


def test_resolve_move_accuracy_variants():
    no_accuracy_move = models.Move(name="Perfect Acc", type="Normal", category="Status", accuracy=None, effects=[])
    assert resolve_move_accuracy(no_accuracy_move, models.GameUnit(current_x=0, current_y=0), None) is None

    plain_move = models.Move(name="Plain Acc", type="Normal", category="Physical", accuracy=80, effects=[])
    assert resolve_move_accuracy(plain_move, models.GameUnit(current_x=0, current_y=0), None) == 80

    conditional_move = models.Move(
        name="Conditional Acc",
        type="Normal",
        category="Physical",
        accuracy=70,
        effects=["conditional_accuracy:weather:sun:100"],
    )
    target = models.GameUnit(current_x=0, current_y=0)
    weather_tiles = [[WEATHER_TO_ID["sun"]]]
    assert resolve_move_accuracy(conditional_move, target, weather_tiles) == 100
    assert resolve_move_accuracy(conditional_move, target, [[0]]) == 70
