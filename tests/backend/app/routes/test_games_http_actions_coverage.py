"""HTTP + helper coverage tests for app.routes.games battle/unit-management endpoints.

Covers: wait, revert_position, end_turn (+ round weather), execute_move (damage,
field weather, miss, validate failure, KO), move, units/place (Conquest + War
preparation), units/{id}/item (add/remove/TM-block), units/{id}/ability,
units/remove/{id}, war/capture (partial + full), plus a few chat/join
error-path checks.

NOTE: GET/PATCH /games/{link}/state are intentionally NOT exercised here.
GameStateSchema and the route handlers filter/serialize using a `player_id`
attribute that does not exist on the GameState model, so calling either
handler raises an AttributeError before a response can be built. Per the
task instructions we skip these two handlers and focus coverage on the
other endpoints instead.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm.attributes import flag_modified

import app.db.models as models
from app.main import app
from app.dependencies import get_db, get_current_user
from app.routes.games import WEATHER_TO_ID


@pytest.fixture
def user(db):
    u = models.User(username="http-user", email="http@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


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
    return {
        "attack": [],
        "defense": [],
        "sp_attack": [],
        "sp_defense": [],
        "speed": [],
        "accuracy": [],
        "evasion": [],
        "crit": [],
    }


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
):
    """Build a full in-progress (or preparation) 2-player battle fixture.

    Returns a dict with: game, state, map_obj, map_state, unit, opponent,
    opponent_unit, move, player, opp_player.
    """
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

    map_state = models.GameMapState(
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


# ---------- /wait ----------


def test_wait_unit_happy_path_advances_turn_when_last_unit(client, db, user):
    ctx = _create_battle_game(db, user, link="wait-1")
    unit = ctx["unit"]

    resp = client.post("/games/wait-1/wait", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["turn_advanced"] is True

    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 1


# ---------- /revert_position ----------


def test_revert_position_moved_unit_reverts_true(client, db, user):
    ctx = _create_battle_game(db, user, link="revert-1")
    unit = ctx["unit"]
    unit.current_x = 2
    unit.current_y = 2
    db.add(unit)
    db.commit()

    resp = client.post("/games/revert-1/revert_position", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reverted"] is True
    assert body["x"] == 1
    assert body["y"] == 1


def test_revert_position_already_at_start_returns_false(client, db, user):
    ctx = _create_battle_game(db, user, link="revert-2")
    unit = ctx["unit"]

    resp = client.post("/games/revert-2/revert_position", json={"unit_id": unit.id})
    assert resp.status_code == 200
    assert resp.json()["reverted"] is False


def test_revert_position_locked_unit_errors(client, db, user):
    ctx = _create_battle_game(db, user, link="revert-3")
    unit = ctx["unit"]
    unit.can_move = False
    db.add(unit)
    db.commit()

    resp = client.post("/games/revert-3/revert_position", json={"unit_id": unit.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unit has already acted"


# ---------- /end_turn ----------


def test_end_turn_happy_path_advances_turn(client, db, user):
    ctx = _create_battle_game(db, user, link="endturn-1")

    resp = client.post("/games/endturn-1/end_turn")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Turn ended"

    db.refresh(ctx["state"])
    assert ctx["state"].current_turn == 1


def test_end_turn_not_your_turn_returns_403(client, db, user):
    ctx = _create_battle_game(db, user, link="endturn-2")

    # First call advances the turn to the opponent; the second call by the
    # same (now non-current) user must be rejected.
    first = client.post("/games/endturn-2/end_turn")
    assert first.status_code == 200

    second = client.post("/games/endturn-2/end_turn")
    assert second.status_code == 403


def test_end_turn_round_end_applies_sandstorm_weather_damage(client, db, user):
    ctx = _create_battle_game(db, user, link="endturn-sand")
    map_state = ctx["map_state"]
    sandstorm_id = WEATHER_TO_ID["sandstorm"]
    map_state.weather_tiles = [[sandstorm_id] * 6 for _ in range(6)]
    db.add(map_state)
    db.commit()

    # Player A ends turn (current_turn 0 -> 1); not a round boundary yet.
    resp_a = client.post("/games/endturn-sand/end_turn")
    assert resp_a.status_code == 200

    # Player B (opponent) ends the round-closing turn; sandstorm should tick.
    app.dependency_overrides[get_current_user] = lambda: ctx["opponent"]
    resp_b = client.post("/games/endturn-sand/end_turn")
    assert resp_b.status_code == 200
    app.dependency_overrides[get_current_user] = lambda: user

    db.refresh(ctx["unit"])
    db.refresh(ctx["opponent_unit"])
    assert ctx["unit"].current_hp < 100
    assert ctx["opponent_unit"].current_hp < 100


# ---------- /execute_move ----------


def test_execute_move_damage_happy_path(client, db, user):
    ctx = _create_battle_game(db, user, link="move-dmg")
    unit = ctx["unit"]
    opponent_unit = ctx["opponent_unit"]

    resp = client.post(
        "/games/move-dmg/execute_move",
        json={
            "unit_id": unit.id,
            "move_id": ctx["move"].id,
            "target_ids": [opponent_unit.id],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["targets"][0]["damage"] > 0

    db.refresh(opponent_unit)
    assert opponent_unit.current_hp < 100


def test_execute_move_field_weather_targets_field(client, db, user):
    ctx = _create_battle_game(db, user, link="move-weather")
    unit = ctx["unit"]

    weather_move = models.Move(
        name="Sandstream-move-weather",
        type="Rock",
        category="Status",
        power=None,
        accuracy=None,
        pp=10,
        effects=["weather:sandstorm"],
        targeting="field",
    )
    db.add(weather_move)
    db.commit()

    unit.flags = {**unit.flags, "move_ids": [ctx["move"].id, weather_move.id]}
    unit.move_pp = [ctx["move"].pp, weather_move.pp]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-weather/execute_move",
        json={"unit_id": unit.id, "move_id": weather_move.id, "target_ids": []},
    )
    assert resp.status_code == 200

    map_state = db.query(models.GameMapState).filter_by(game_id=ctx["game"].id).first()
    assert map_state.weather_tiles[unit.current_y][unit.current_x] == WEATHER_TO_ID["sandstorm"]


def test_execute_move_miss_with_zero_accuracy(client, db, user):
    ctx = _create_battle_game(db, user, link="move-miss")
    unit = ctx["unit"]
    opponent_unit = ctx["opponent_unit"]

    miss_move = models.Move(
        name="AlwaysMiss-move-miss",
        type="Normal",
        category="Physical",
        power=40,
        accuracy=0,
        pp=10,
        effects=[],
        targeting="enemy",
    )
    db.add(miss_move)
    db.commit()

    unit.flags = {**unit.flags, "move_ids": [miss_move.id]}
    unit.move_pp = [miss_move.pp]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-miss/execute_move",
        json={"unit_id": unit.id, "move_id": miss_move.id, "target_ids": [opponent_unit.id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["missed_target_ids"] == [opponent_unit.id]

    db.refresh(opponent_unit)
    assert opponent_unit.current_hp == 100


def test_execute_move_validate_fail_requires_type(client, db, user):
    ctx = _create_battle_game(db, user, link="move-fail")
    unit = ctx["unit"]
    opponent_unit = ctx["opponent_unit"]

    fire_only_move = models.Move(
        name="FireOnly-move-fail",
        type="Fire",
        category="Status",
        power=None,
        accuracy=None,
        pp=10,
        effects=["requires:type:fire"],
        targeting="enemy",
    )
    db.add(fire_only_move)
    db.commit()

    unit.flags = {**unit.flags, "move_ids": [fire_only_move.id]}
    unit.move_pp = [fire_only_move.pp]
    db.add(unit)
    db.commit()

    resp = client.post(
        "/games/move-fail/execute_move",
        json={"unit_id": unit.id, "move_id": fire_only_move.id, "target_ids": [opponent_unit.id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["detail"] == "Move failed"
    assert body["message"] == "But it failed"


def test_execute_move_ko_last_enemy_completes_game(client, db, user):
    ctx = _create_battle_game(db, user, link="move-ko")
    unit = ctx["unit"]
    opponent_unit = ctx["opponent_unit"]
    opponent_unit.current_hp = 5
    db.add(opponent_unit)
    db.commit()

    resp = client.post(
        "/games/move-ko/execute_move",
        json={"unit_id": unit.id, "move_id": ctx["move"].id, "target_ids": [opponent_unit.id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert opponent_unit.id in body["removed_ids"]

    db.refresh(ctx["state"])
    assert ctx["state"].status == models.GameStatus.completed
    assert ctx["state"].winner_id == user.id


# ---------- /move ----------


def test_move_unit_to_allowed_tile(client, db, user, _mock_redis):
    ctx = _create_battle_game(db, user, link="move-basic")
    unit = ctx["unit"]
    sx, sy = unit.current_x, unit.current_y
    nx, ny = sx + 1, sy

    _mock_redis.hget.return_value = json.dumps({"origin": [sx, sy], "tiles": [[nx, ny], [sx, sy]]})

    resp = client.post("/games/move-basic/move", json={"unit_id": unit.id, "x": nx, "y": ny})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["x"] == nx
    assert body["y"] == ny

    db.refresh(unit)
    assert (unit.current_x, unit.current_y) == (nx, ny)


# ---------- /units/place ----------


def test_place_unit_conquest_with_enough_cash(client, db, user):
    ctx = _create_battle_game(db, user, link="place-1", gamemode="Conquest")
    unit_info = _make_unit_definition(db, link="place-1", suffix="new", cost=100)
    db.commit()

    resp = client.post(
        "/games/place-1/units/place",
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
    assert body["unit_id"] == unit_info.id

    db.refresh(ctx["player"])
    assert ctx["player"].cash_remaining == 900


def test_place_unit_not_enough_cash_errors(client, db, user):
    ctx = _create_battle_game(db, user, link="place-2", gamemode="Conquest")
    ctx["player"].cash_remaining = 10
    db.add(ctx["player"])
    db.commit()

    expensive_unit = _make_unit_definition(db, link="place-2", suffix="pricey", cost=500)
    db.commit()

    resp = client.post(
        "/games/place-2/units/place",
        json={
            "unit_id": expensive_unit.id,
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
    assert resp.json()["detail"] == "Not enough cash"


def test_place_unit_war_preparation_on_owned_objective(client, db, user):
    ctx = _create_battle_game(db, user, link="place-war", gamemode="War", preparation=True)
    map_state = ctx["map_state"]
    map_state.objective_tiles[0][0] = {"owner": 1, "kind": "pokeball", "hp": 10, "max_hp": 10}
    flag_modified(map_state, "objective_tiles")
    db.add(map_state)
    db.commit()

    unit_info = _make_unit_definition(db, link="place-war", suffix="warrior", cost=100)
    db.commit()

    resp = client.post(
        "/games/place-war/units/place",
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
    # Preparation-phase placements are not war "summons", so they stay unlocked.
    assert body["can_move"] is True
    assert body["current_x"] == 0
    assert body["current_y"] == 0


# ---------- /units/{id}/item ----------


def test_change_unit_item_add_and_remove_berry_in_preparation(client, db, user):
    ctx = _create_battle_game(db, user, link="item-1", preparation=True)
    unit = ctx["unit"]
    berry = models.Item(name="Oran Berry item-1", slug="oran_berry_item_1", category="berry", cost=50)
    db.add(berry)
    db.commit()

    resp = client.post(f"/games/item-1/units/{unit.id}/item", json={"item_id": berry.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["unit"]["held_item_slug"] == berry.slug
    assert body["cash_remaining"] == 1000 - berry.cost

    resp2 = client.delete(f"/games/item-1/units/{unit.id}/item")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["unit"]["held_item_slug"] is None
    assert body2["cash_remaining"] == 1000


def test_change_unit_item_tm_blocked_when_start_with_tms_false(client, db, user):
    ctx = _create_battle_game(db, user, link="item-2", preparation=True)
    unit = ctx["unit"]
    assert ctx["game"].start_with_tms is False

    tm_move = models.Move(name="TM Move item-2", type="Water", category="Special", pp=10)
    db.add(tm_move)
    db.commit()
    tm_item = models.Item(name="TM01 item-2", slug="tm01_item_2", category="tm", cost=500, move_id=tm_move.id)
    db.add(tm_item)
    db.commit()

    resp = client.post(f"/games/item-2/units/{unit.id}/item", json={"item_id": tm_item.id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "TM items are not enabled for this game"


# ---------- /units/{id}/ability ----------


def test_change_unit_ability_in_preparation(client, db, user):
    ctx = _create_battle_game(db, user, link="ability-1", preparation=True)
    unit = ctx["unit"]

    ability1 = models.Ability(name="Overgrow", slug="overgrow-ability-1", generation=1)
    ability2 = models.Ability(name="Chlorophyll", slug="chlorophyll-ability-1", generation=1)
    db.add_all([ability1, ability2])
    db.commit()

    unit_info = db.query(models.Unit).filter_by(id=unit.unit_id).first()
    unit_info.ability_ids = [ability1.id, ability2.id]
    db.add(unit_info)
    db.commit()

    resp = client.post(f"/games/ability-1/units/{unit.id}/ability", json={"ability_id": ability2.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["unit"]["ability_id"] == ability2.id
    assert body["unit"]["ability"] == "Chlorophyll"


# ---------- /units/remove/{id} ----------


def test_remove_unit_in_preparation_refunds_cash(client, db, user):
    ctx = _create_battle_game(db, user, link="remove-1", preparation=True)
    unit = ctx["unit"]
    unit_info = db.query(models.Unit).filter_by(id=unit.unit_id).first()
    cost = unit_info.cost
    starting_cash = ctx["player"].cash_remaining

    resp = client.delete(f"/games/remove-1/units/remove/{unit.id}")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Unit removed and cash refunded"

    db.refresh(ctx["player"])
    assert ctx["player"].cash_remaining == starting_cash + cost
    assert db.query(models.GameUnit).filter_by(id=unit.id).first() is None


# ---------- /war/capture ----------


def test_capture_objective_deals_damage_without_full_capture(client, db, user):
    ctx = _create_battle_game(db, user, link="capture-1", gamemode="War")
    map_state = ctx["map_state"]
    unit = ctx["unit"]
    unit.current_hp = 50  # half of max HP (100) -> partial capture damage
    db.add(unit)
    map_state.objective_tiles[unit.current_y][unit.current_x] = {
        "owner": 2,
        "kind": "pokeball",
        "hp": 20,
        "max_hp": 20,
    }
    flag_modified(map_state, "objective_tiles")
    db.add(map_state)
    db.commit()

    resp = client.post("/games/capture-1/war/capture", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["captured"] is False
    assert body["objective"]["hp"] == 15
    assert body["objective"]["owner"] == 2


def test_capture_objective_full_capture(client, db, user):
    ctx = _create_battle_game(db, user, link="capture-2", gamemode="War")
    map_state = ctx["map_state"]
    unit = ctx["unit"]  # full HP (100/100) -> maximum capture damage
    map_state.objective_tiles[unit.current_y][unit.current_x] = {
        "owner": 2,
        "kind": "pokeball",
        "hp": 5,
        "max_hp": 20,
    }
    flag_modified(map_state, "objective_tiles")
    db.add(map_state)
    db.commit()

    resp = client.post("/games/capture-2/war/capture", json={"unit_id": unit.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["captured"] is True
    assert body["objective"]["owner"] == 1
    assert body["objective"]["hp"] == 20


# ---------- /turnlock ----------


def test_get_turnlock_returns_empty_dict_when_no_locks_cached(client, db, user, _mock_redis):
    _create_battle_game(db, user, link="turnlock-1")
    _mock_redis.hgetall.return_value = {}

    resp = client.get("/games/turnlock-1/turnlock")
    assert resp.status_code == 200
    assert resp.json() == {}


# ---------- /chat and /join error paths ----------


def test_chat_empty_message_is_rejected(client, db, user):
    _create_battle_game(db, user, link="chat-1")

    resp = client.post("/games/chat-1/chat", json={"message": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Message cannot be empty"


def test_join_full_game_is_rejected(client, db, user):
    ctx = _create_battle_game(db, user, link="join-full", status=models.GameStatus.open)
    game = ctx["game"]
    game.max_players = 2
    db.add(game)
    db.commit()

    third_user = models.User(username="third-join", email="third-join@example.com", hashed_password="x")
    db.add(third_user)
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: third_user
    resp = client.post(f"/games/join/{game.id}")
    app.dependency_overrides[get_current_user] = lambda: user

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Game is full"
