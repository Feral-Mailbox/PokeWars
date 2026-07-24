"""Raise games.py coverage via helper unit tests and thin HTTP list/player routes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.db.models as models
from app.dependencies import get_current_user, get_db
from app.main import app
from app.routes import games as games_mod
from app.routes.games import (
    FIELD_HAZARD_STACK_LIMITS,
    WEATHER_TO_ID,
    _initialize_war_objective_tiles,
    append_replay_log_event,
    clear_hazards_on_tiles,
    clear_substitutes_on_tiles,
    clear_terrain_at_position,
    consume_unit_held_item,
    decrement_and_expire_hazards,
    estimate_damage_for_mode,
    faint_unit_in_place,
    find_revival_placement_tile,
    format_stat_change_outcome_phrase,
    format_stat_log_label,
    format_state_log_message,
    format_status_log_label,
    get_draw_player_ids,
    get_hazard_entries_at_position,
    get_pulse_tiles_backend,
    get_remaining_unit_counts,
    get_stat_multiplier,
    get_unit_learnset_move_ids,
    get_unboosted_battle_stat,
    get_username_by_id,
    get_weather_defense_multiplier,
    get_weather_move_multiplier,
    get_weather_name_from_id,
    increment_allies_defeated_since_turn,
    is_ability_suppressed,
    is_item_suppressed,
    is_movement_locked,
    maybe_restore_war_objectives_at_turn_end,
    move_is_instant_ko,
    normalize_hazard_cell,
    publish_chat_message_event,
    publish_game_ws_event,
    publish_map_state_updated,
    publish_objective_cell_updated,
    publish_player_state_updated,
    publish_system_log_event,
    publish_turn_remaining_warning_if_needed,
    remove_unit_held_item,
    set_movement_locked,
    set_unit_held_item,
    try_add_hazard_stack,
    unit_holds_item_type,
    unit_stats_lowered_since_turn_start,
    unit_stats_raised_since_turn_start,
)


@pytest.fixture
def user(db):
    u = models.User(username="wave2-user", email="wave2@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def client(db, user):
    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _unit_def(db, *, name="Wave Mon", types=None, species_id=9100):
    unit = models.Unit(
        species_id=species_id + db.query(models.Unit).count(),
        name=name,
        species=name,
        asset_folder=name.lower().replace(" ", "_"),
        types=types or ["Normal"],
        base_stats={"hp": 50, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50, "speed": 50},
        level_up_moves=[{"level": 1, "move_id": 10}, {"level": 5, "move_id": 11}],
        tm_moves=[20, 21],
        egg_moves=[30],
        equipped_moves=[10],
        ability_ids=[],
        cost=100,
    )
    db.add(unit)
    db.flush()
    return unit


def _seed_listed_game(db, user, *, status, link, gamemode="Conquest", is_private=False):
    map_obj = models.Map(
        name=f"Map {link}",
        creator_id=user.id,
        is_official=True,
        width=3,
        height=3,
        tileset_names=["grass"],
        tile_data={},
        allowed_modes=[gamemode],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.flush()
    game = models.Game(
        game_name=f"Game {link}",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode=gamemode,
        is_private=is_private,
        host_id=user.id,
        link=link,
    )
    db.add(game)
    db.flush()
    db.add(
        models.GameState(
            game_id=game.id,
            current_turn=0,
            status=status,
            players=[user.id],
            replay_log=[],
        )
    )
    db.add(
        models.GamePlayer(
            game_id=game.id,
            player_id=user.id,
            cash_remaining=500,
            game_units=[],
            is_ready=False,
        )
    )
    db.commit()
    return game


# ---------- Redis / publish helpers ----------


def test_movement_lock_helpers(_mock_redis):
    _mock_redis.get.return_value = None
    assert is_movement_locked("g1", 7) is False
    set_movement_locked("g1", 7)
    _mock_redis.set.assert_called()
    _mock_redis.get.return_value = "1"
    assert is_movement_locked("g1", 7) is True


def test_publish_helpers_success_and_exception(_mock_redis):
    publish_game_ws_event("link-a", {"event": "x"})
    publish_player_state_updated("link-a")
    publish_map_state_updated("link-a")
    publish_objective_cell_updated("link-a", 1, 2, {"hp": 10, "owner": 3, "kind": "pokeball"})
    assert _mock_redis.publish.called

    _mock_redis.publish.side_effect = RuntimeError("redis down")
    publish_game_ws_event("link-a", {"event": "y"})
    publish_player_state_updated("link-a")
    publish_map_state_updated("link-a")
    publish_objective_cell_updated("link-a", 0, 0, {})


def test_replay_chat_system_and_turn_warning(db, user, _mock_redis):
    assert append_replay_log_event(None, {"event": "x"}) is None

    state = models.GameState(game_id=1, current_turn=0, status=models.GameStatus.in_progress, players=[user.id], replay_log=[])
    # Bound replay log truncation path
    state.replay_log = [{"n": i} for i in range(501)]
    append_replay_log_event(state, {"event": "trim"})
    assert len(state.replay_log) == 500

    game = models.Game(link="warn-link", turn_seconds=45, gamemode="Conquest", host_id=user.id, map_id=1, map_name="m", max_players=2)
    publish_chat_message_event("warn-link", user.id, user.username, "hi", state, db)
    publish_system_log_event("warn-link", "sys", state, db)

    now = datetime.now(timezone.utc)
    state.turn_deadline = now + timedelta(seconds=20)
    state.status = models.GameStatus.in_progress
    state.players = [user.id]
    state.current_turn = 0
    state.replay_log = [{"event": "system_log", "warning_type": "other"}]
    assert publish_turn_remaining_warning_if_needed(game, state, db, now) is True

    # Duplicate warning short-circuits
    assert publish_turn_remaining_warning_if_needed(game, state, db, now) is False

    state.status = models.GameStatus.open
    assert publish_turn_remaining_warning_if_needed(game, state, db, now) is False

    assert get_username_by_id(user.id, db) == user.username
    assert get_username_by_id(999999, db) == "Player 999999"


def test_war_objective_helpers(db, user, monkeypatch):
    game = models.Game(link="war1", gamemode="War", host_id=user.id, map_id=1, map_name="m", max_players=2)
    state = models.GameState(game_id=1, current_turn=0, status=models.GameStatus.in_progress, players=[user.id])
    map_state = models.GameMapState(game_id=1, map_id=1, objective_tiles=[])
    map_obj = models.Map(name="w", width=2, height=2, tileset_names=[], tile_data={}, creator_id=user.id)

    monkeypatch.setattr(games_mod, "is_war_game", lambda _g: False)
    maybe_restore_war_objectives_at_turn_end(game, db)
    _initialize_war_objective_tiles(game, state, map_state, map_obj)

    monkeypatch.setattr(games_mod, "is_war_game", lambda _g: True)
    monkeypatch.setattr(games_mod, "restore_unoccupied_damaged_objectives", lambda *_a, **_k: [])
    maybe_restore_war_objectives_at_turn_end(game, db)

    restored = [(0, 0, {"hp": 5, "owner": 1, "kind": "pokeball"})]
    monkeypatch.setattr(games_mod, "restore_unoccupied_damaged_objectives", lambda *_a, **_k: restored)
    # No map_state in db → early return
    maybe_restore_war_objectives_at_turn_end(game, db)

    db.add(user)
    db.flush()
    map_row = models.Map(
        name="War Map",
        creator_id=user.id,
        is_official=True,
        width=2,
        height=2,
        tileset_names=["g"],
        tile_data={},
        allowed_modes=["War"],
        allowed_player_counts=[2],
    )
    db.add(map_row)
    db.flush()
    war_game = models.Game(
        game_name="War G",
        map_id=map_row.id,
        map_name=map_row.name,
        max_players=2,
        gamemode="War",
        is_private=False,
        host_id=user.id,
        link="war-cov",
    )
    db.add(war_game)
    db.flush()
    ms = models.GameMapState(
        game_id=war_game.id,
        map_id=map_row.id,
        objective_tiles=[[[0, 0], [0, 0]], [[0, 0], [0, 0]]],
        weather_tiles=[[0, 0], [0, 0]],
        hazard_tiles=[[[], []], [[], []]],
        room_effect_tiles=[[0, 0], [0, 0]],
        terrain_effect_tiles=[[0, 0], [0, 0]],
        field_effect_tiles=[[0, 0], [0, 0]],
        item_id_tiles=[[None, None], [None, None]],
    )
    db.add(ms)
    db.commit()
    monkeypatch.setattr(
        games_mod,
        "restore_unoccupied_damaged_objectives",
        lambda *_a, **_k: [(0, 1, {"hp": 8, "owner": 2})],
    )
    maybe_restore_war_objectives_at_turn_end(war_game, db)

    monkeypatch.setattr(
        games_mod,
        "build_objective_tiles_from_map",
        lambda *_a, **_k: [[[1, 1], [0, 0]], [[0, 0], [1, 2]]],
    )
    monkeypatch.setattr(games_mod, "mark_master_ball_original_owners", lambda *_a, **_k: None)
    gs = models.GameState(game_id=war_game.id, current_turn=0, status=models.GameStatus.in_progress, players=[user.id])
    _initialize_war_objective_tiles(war_game, gs, ms, map_row)
    assert ms.objective_tiles[0][0] == [1, 1]


# ---------- Item / stat / ability helpers ----------


def test_learnset_item_stat_helpers(db):
    info = _unit_def(db)
    assert 10 in get_unit_learnset_move_ids(info)
    assert 20 in get_unit_learnset_move_ids(info)
    assert 30 in get_unit_learnset_move_ids(info)

    unit = models.GameUnit(flags={}, states=[], status_effects=[], stat_boosts={})
    assert unit_holds_item_type(unit, "berry") is False
    set_unit_held_item(unit, "oran_berry", db)
    assert unit_holds_item_type(unit, "berry") is True
    assert remove_unit_held_item(unit, db) is True
    assert remove_unit_held_item(unit, db) is False

    set_unit_held_item(unit, "sitrus_berry", db)
    assert consume_unit_held_item(unit, db, item_type="orb") is False
    assert consume_unit_held_item(unit, db, item_type="berry") is True

    set_unit_held_item(unit, "leftovers", db)
    unit.states = ["embargo", 2]
    assert is_item_suppressed(unit) is True
    assert consume_unit_held_item(unit, db) is False
    unit.states = ["gastro_acid", 1]
    assert is_ability_suppressed(unit) is True
    unit.states = []
    assert is_ability_suppressed(unit) is False
    assert is_item_suppressed(unit) is False

    unit.flags = {"stat_stages_at_turn_start": {"attack": 1, "defense": 0}}
    unit.stat_boosts = {"attack": [{"magnitude": 0, "expires_turn": 4}]}
    assert unit_stats_lowered_since_turn_start(unit) is True
    unit.stat_boosts = {"attack": [{"magnitude": 2, "expires_turn": 4}]}
    assert unit_stats_raised_since_turn_start(unit) is True
    unit.flags = {}
    assert unit_stats_lowered_since_turn_start(unit) is False
    assert unit_stats_raised_since_turn_start(unit) is False


def test_faint_allies_and_remaining_counts(db, user):
    info = _unit_def(db)
    game = models.Game(
        game_name="faint-g",
        map_id=1,
        map_name="m",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="faint-link",
    )
    db.add(game)
    db.flush()
    ally = models.GameUnit(
        game_id=game.id,
        user_id=user.id,
        unit_id=info.id,
        current_hp=40,
        is_fainted=False,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        flags={"allies_defeated_since_turn": 0},
        states=[],
        status_effects=[],
        stat_boosts={},
        current_stats={"attack": 80, "defense": 50},
        level=50,
    )
    fainted = models.GameUnit(
        game_id=game.id,
        user_id=user.id,
        unit_id=info.id,
        current_hp=10,
        is_fainted=False,
        starting_x=1,
        starting_y=0,
        current_x=1,
        current_y=0,
        flags={},
        states=[],
        status_effects=[],
        stat_boosts={},
        current_stats={"attack": 40},
        level=50,
    )
    db.add_all([ally, fainted])
    db.commit()

    increment_allies_defeated_since_turn(fainted, db)
    db.commit()
    db.refresh(ally)
    assert ally.flags["allies_defeated_since_turn"] == 1

    faint_unit_in_place(fainted, db)
    db.commit()
    assert fainted.is_fainted is True
    assert fainted.current_x == -1
    counts = get_remaining_unit_counts(game.id, db)
    assert counts[user.id] == 1

    game_state = models.GameState(
        game_id=game.id,
        current_turn=0,
        status=models.GameStatus.in_progress,
        players=[user.id],
    )
    assert get_draw_player_ids(game, game_state, db) == [user.id]


def test_format_and_weather_hazard_helpers(db, user):
    assert format_stat_log_label("all") == "all stats"
    assert format_stat_log_label("attack")
    assert format_status_log_label("burn")
    assert format_stat_change_outcome_phrase(1, 1) == "rose."
    assert format_stat_change_outcome_phrase(2, 1) == "rose sharply."
    assert format_stat_change_outcome_phrase(3, 1) == "rose drastically."
    assert format_stat_change_outcome_phrase(-1, -1) == "fell."
    assert format_stat_change_outcome_phrase(-2, -1) == "harshly fell."
    assert format_stat_change_outcome_phrase(-3, -1) == "severely fell."
    assert format_stat_change_outcome_phrase(0, 1) == "won't go higher."
    assert format_stat_change_outcome_phrase(0, -1) == "won't go lower."

    info = _unit_def(db, name="LogMon")
    unit = models.GameUnit(user_id=user.id, unit_id=info.id, unit=info)
    assert "flinched" in format_state_log_message(unit, "flinch", db)
    assert "confused" in format_state_log_message(unit, "confusion", db)
    assert "gained sleep" in format_state_log_message(unit, "sleep", db)

    assert get_weather_name_from_id(WEATHER_TO_ID["rain"]) == "rain"
    assert get_weather_name_from_id(999) == "clear"
    assert get_weather_move_multiplier("water", WEATHER_TO_ID["rain"]) == 1.5
    assert get_weather_move_multiplier("fire", WEATHER_TO_ID["rain"]) == 0.5
    assert get_weather_move_multiplier("fire", WEATHER_TO_ID["sun"]) == 1.5
    assert get_weather_move_multiplier("water", WEATHER_TO_ID["sun"]) == 0.5
    assert get_weather_move_multiplier("normal", WEATHER_TO_ID["rain"]) == 1.0

    rock = _unit_def(db, name="RockMon", types=["Rock"], species_id=9200)
    ice = _unit_def(db, name="IceMon", types=["Ice"], species_id=9300)
    rock_unit = models.GameUnit(unit_id=rock.id, unit=rock)
    ice_unit = models.GameUnit(unit_id=ice.id, unit=ice)
    assert get_weather_defense_multiplier(rock_unit, "sp_defense", WEATHER_TO_ID["sandstorm"], db) == 1.5
    assert get_weather_defense_multiplier(ice_unit, "defense", WEATHER_TO_ID["hail"], db) == 1.5
    assert get_weather_defense_multiplier(ice_unit, "sp_defense", WEATHER_TO_ID["hail"], db) == 1.0

    assert normalize_hazard_cell(None) == []
    assert normalize_hazard_cell([[1, 3], ["bad"], [0, 2], [2]]) == [[1, 3]]
    entries = []
    assert try_add_hazard_stack(entries, 1, 5) is True
    assert try_add_hazard_stack(entries, 0, 5) is False
    for _ in range(FIELD_HAZARD_STACK_LIMITS[1]):
        try_add_hazard_stack(entries, 1, 5)
    assert try_add_hazard_stack(entries, 1, 5) is False

    hazards = [[[ [1, 2] ], []], [[], []]]
    assert get_hazard_entries_at_position(hazards, 0, 0) == [[1, 2]]
    assert get_hazard_entries_at_position(hazards, -1, 0) == []

    assert get_stat_multiplier({}, "attack") == 1.0
    assert get_stat_multiplier({"attack": [{"magnitude": 2, "expires_turn": 4}]}, "attack") == 2.0
    assert get_stat_multiplier({"attack": [{"magnitude": -2, "expires_turn": 4}]}, "attack") == 0.5

    assert estimate_damage_for_mode(
        power=80, level=50, attack=100, defense=0, stab=1.5, type_multiplier=2.0, weather_move_multiplier=1.0, targets_multiplier=1.0
    ) > 0

    assert move_is_instant_ko(models.Move(name="KO", type="Ice", category="Special", effects=["target:instant_ko"]))
    assert move_is_instant_ko(models.Move(name="Nope", type="Normal", category="Physical", effects=["target:burn"])) is False
    assert move_is_instant_ko(None) is False

    tiles = get_pulse_tiles_backend(2, 2, 1, 5, 5)
    assert (2, 1) in tiles and (2, 2) not in tiles
    assert (2, 2) in get_pulse_tiles_backend(2, 2, 3, 5, 5)
    assert len(get_pulse_tiles_backend(2, 2, 4, 5, 5)) > len(tiles)


def test_terrain_hazard_substitute_revival(db, user):
    map_obj = models.Map(
        name="Haz Map",
        creator_id=user.id,
        is_official=True,
        width=3,
        height=3,
        tileset_names=["g"],
        tile_data={},
        allowed_modes=["Conquest"],
        allowed_player_counts=[2],
    )
    db.add(map_obj)
    db.flush()
    game = models.Game(
        game_name="Haz G",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="haz-link",
    )
    db.add(game)
    db.flush()
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=map_obj.id,
        weather_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        hazard_tiles=[[[ [1, 2] ], [], []], [[], [], []], [[], [], []]],
        room_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        terrain_effect_tiles=[[[1, 3], 0, 0], [0, 0, 0], [0, 0, 0]],
        field_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        item_id_tiles=[[None, None, None], [None, None, None], [None, None, None]],
    )
    db.add(map_state)
    info = _unit_def(db, name="SubMon")
    unit = models.GameUnit(
        game_id=game.id,
        user_id=user.id,
        unit_id=info.id,
        current_hp=50,
        is_fainted=False,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        states=["substitute", 5],
        flags={},
        status_effects=[],
        stat_boosts={},
        current_stats={"attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50},
        level=50,
    )
    db.add(unit)
    db.commit()

    clear_terrain_at_position(map_state, 0, 0, db)
    assert map_state.terrain_effect_tiles[0][0] == [0, 0]
    clear_terrain_at_position(map_state, -1, 0, db)

    assert clear_hazards_on_tiles(map_state, [(0, 0), (9, 9)], db) is True
    assert map_state.hazard_tiles[0][0] == []

    map_state.hazard_tiles = [[[ [1, 1] ], []], [[], []]]
    db.add(map_state)
    db.commit()
    assert decrement_and_expire_hazards(game.id, db) is True

    game_state = models.GameState(
        game_id=game.id,
        current_turn=0,
        status=models.GameStatus.in_progress,
        players=[user.id],
        replay_log=[],
    )
    db.add(game_state)
    db.commit()
    assert clear_substitutes_on_tiles(game.id, [(0, 0)], db, game=game, game_state=game_state) is True
    db.commit()
    db.refresh(unit)
    assert unit.states == []

    unit.current_x = 1
    unit.current_y = 1
    unit.is_fainted = False
    unit.current_hp = 40
    db.add(unit)
    db.commit()
    tile = find_revival_placement_tile(unit, map_obj, db, pulse=3)
    assert tile is not None

    boosted = models.GameUnit(
        unit_id=info.id,
        unit=info,
        current_stats={"attack": 100},
        stat_boosts={"attack": [{"magnitude": 2, "expires_turn": 4}]},
        level=50,
        flags={},
        states=[],
        status_effects=[],
    )
    # Without full compute_effective_stats wiring, unboosted may still return a value or 0.
    value = get_unboosted_battle_stat(boosted, "attack", db)
    assert isinstance(value, int)


# ---------- HTTP list / player routes ----------


def test_list_game_status_endpoints(client, db, user):
    _seed_listed_game(db, user, status=models.GameStatus.closed, link="closed-1")
    _seed_listed_game(db, user, status=models.GameStatus.in_progress, link="prog-1")
    _seed_listed_game(db, user, status=models.GameStatus.preparation, link="prep-1")
    _seed_listed_game(db, user, status=models.GameStatus.completed, link="done-1")
    _seed_listed_game(db, user, status=models.GameStatus.closed, link="priv-1", is_private=True)

    assert any(g["link"] == "closed-1" for g in client.get("/games/closed").json())
    links = {g["link"] for g in client.get("/games/in_progress").json()}
    assert "prog-1" in links and "prep-1" in links
    assert any(g["link"] == "done-1" for g in client.get("/games/completed").json())
    assert all(g["link"] != "priv-1" for g in client.get("/games/closed").json())


def test_player_ready_units_and_join(client, db, user):
    game = _seed_listed_game(db, user, status=models.GameStatus.preparation, link="ready-1")
    map_state = models.GameMapState(
        game_id=game.id,
        map_id=game.map_id,
        weather_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        hazard_tiles=[[[], [], []], [[], [], []], [[], [], []]],
        room_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        terrain_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        field_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        item_id_tiles=[[None, None, None], [None, None, None], [None, None, None]],
    )
    db.add(map_state)
    info = _unit_def(db, name="ReadyMon")
    db.add(
        models.GameUnit(
            game_id=game.id,
            user_id=user.id,
            unit_id=info.id,
            current_hp=50,
            is_fainted=False,
            starting_x=0,
            starting_y=0,
            current_x=0,
            current_y=0,
            flags={},
            states=[],
            status_effects=[],
            stat_boosts={},
            current_stats={"hp": 50},
            level=50,
            can_move=True,
        )
    )
    db.commit()

    player = client.get("/games/ready-1/player")
    assert player.status_code == 200
    assert player.json()["cash_remaining"] == 500

    ready = client.post("/games/ready-1/player/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    unready = client.post("/games/ready-1/player/ready")
    assert unready.json()["ready"] is False

    units = client.get("/games/ready-1/units")
    assert units.status_code == 200
    assert len(units.json()) >= 1

    chat = client.post("/games/ready-1/chat", json={"message": "hello team"})
    assert chat.status_code == 200

    turnlock = client.get("/games/ready-1/turnlock")
    assert turnlock.status_code == 200

    # Join requires an open lobby
    open_game = _seed_listed_game(db, user, status=models.GameStatus.open, link="join-open")
    db.add(
        models.GameMapState(
            game_id=open_game.id,
            map_id=open_game.map_id,
            weather_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            hazard_tiles=[[[], [], []], [[], [], []], [[], [], []]],
            room_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            terrain_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            field_effect_tiles=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            item_id_tiles=[[None, None, None], [None, None, None], [None, None, None]],
        )
    )
    other = models.User(username="joiner", email="joiner@example.com", hashed_password="x")
    db.add(other)
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: other
    join = client.post(f"/games/join/{open_game.id}")
    assert join.status_code == 200
    app.dependency_overrides[get_current_user] = lambda: user
