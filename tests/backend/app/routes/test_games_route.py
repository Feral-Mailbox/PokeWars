# tests/apps/backend/app/routes/test_games_route.py
import pytest
import app.db.models as models
from fastapi.testclient import TestClient
from app.routes.games import (
    process_move_effects,
    decrement_and_expire_status_effects,
    move_deals_direct_damage,
    movement_range_backend,
    apply_damage_based_move_effects,
)

from app.main import app
from app.dependencies import get_db, get_current_user

@pytest.fixture(scope="function")
def user(db):
    u = models.User(
        username="player1",
        email="player1@example.com",
        hashed_password="hashed"
    )
    db.add(u)
    db.commit()
    return u

@pytest.fixture(scope="function")
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
    
# ---------- Tests ----------

def test_create_game(client, db, user):
    # Insert a test map first
    map = models.Map(
        name="Test Map",
        creator_id=user.id,
        is_official=True,
        width=10,
        height=10,
        tileset_names=["grass"],
        tile_data={},
        allowed_modes=["Conquest"],
        allowed_player_counts=[2]
    )
    db.add(map)
    db.commit()

    resp = client.post("/games/create", json={
        "game_name": "My Game",
        "map_name": "Test Map",
        "max_players": 2,
        "is_private": False,
        "gamemode": "Conquest"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["game_name"] == "My Game"
    assert data["map_name"] == "Test Map"
    assert data["players"][0]["username"] == "player1"
    assert data["gamemode"] == "Conquest"

def test_get_open_games(client, db, user):
    # Create an open game
    map = models.Map(
        name="Test Map",
        creator_id=user.id,
        is_official=True,
        width=10,
        height=10,
        tileset_names=["grass"],
        tile_data={},
        allowed_modes=["Conquest"],
        allowed_player_counts=[2]
    )
    db.add(map)
    db.commit()

    game = models.Game(
        game_name="Game A",
        map_id=map.id,
        map_name=map.name,
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="abc123"
    )
    db.add(game)
    db.flush()

    state = models.GameState(
        game_id=game.id,
        current_turn=0,
        status=models.GameStatus.open,
        players=[user.id],
        winner_id=None,
        replay_log=[]
    )
    db.add(state)

    player_state = models.GamePlayer(
        game_id=game.id,
        player_id=user.id,
        cash_remaining=0,
        game_units=[],
        is_ready=False
    )
    db.add(player_state)

    db.commit()

    resp = client.get("/games/open")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["game_name"] == "Game A"

def test_get_game_by_link(client, db, user):
    # Create everything needed
    map = models.Map(
        name="Deep Woods",
        creator_id=user.id,
        is_official=True,
        width=10,
        height=10,
        tileset_names=["forest"],
        tile_data={},
        allowed_modes=["Conquest"],
        allowed_player_counts=[2]
    )
    db.add(map)
    db.commit()

    game = models.Game(
        game_name="Forest Battle",
        map_id=map.id,
        map_name="Deep Woods",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="forest123"
    )
    db.add(game)
    db.flush()

    db.add(models.GameState(
        game_id=game.id,
        current_turn=1,
        status=models.GameStatus.open,
        players=[user.id],
        winner_id=None,
        replay_log=[]
    ))

    db.add(models.GamePlayer(
        game_id=game.id,
        player_id=user.id,
        cash_remaining=100,
        game_units=[],
        is_ready=False
    ))

    db.commit()

    resp = client.get("/games/forest123")
    assert resp.status_code == 200
    assert resp.json()["game_name"] == "Forest Battle"


def test_process_move_effects_applies_status_to_target(db):
    move = models.Move(
        name="Status Test",
        type="ghost",
        category="Status",
        effects=["target:status:burn"]
    )
    attacker = models.GameUnit(status_effects=[])
    target = models.GameUnit(status_effects=[], current_hp=100)

    process_move_effects(move, attacker, [target], current_turn=0, db=db)

    assert isinstance(target.status_effects, list)
    assert len(target.status_effects) == 2
    assert target.status_effects[0] == "burn"
    assert 4 <= target.status_effects[1] <= 7


def test_process_move_effects_does_not_override_existing_status(db):
    move = models.Move(
        name="Status Test 2",
        type="psychic",
        category="Status",
        effects=["target:status:sleep"]
    )
    attacker = models.GameUnit(status_effects=[])
    target = models.GameUnit(
        status_effects=["poison", 3],
        current_hp=100
    )

    process_move_effects(move, attacker, [target], current_turn=0, db=db)

    assert target.status_effects[0] == "poison"
    assert target.status_effects[1] == 3


def make_unit_definition(unit_types):
    return models.Unit(
        species_id=999,
        form_id=None,
        name="Testmon",
        species="Testmon",
        asset_folder="testmon",
        types=unit_types,
        base_stats={"hp": 100},
        move_ids=[],
        ability_ids=[],
        cost=0,
        portrait_credits=[],
        sprite_credits=[]
    )


@pytest.mark.parametrize(
    "status_name,unit_types",
    [
        ("paralysis", ["electric"]),
        ("poison", ["poison"]),
        ("badly_poison", ["steel"]),
        ("burn", ["fire"]),
        ("frozen", ["ice"]),
    ],
)
def test_process_move_effects_respects_type_status_immunities(db, status_name, unit_types):
    move = models.Move(
        name=f"Status {status_name}",
        type="normal",
        category="Status",
        effects=[f"target:status:{status_name}"]
    )
    attacker = models.GameUnit(status_effects=[])
    target = models.GameUnit(
        status_effects=[],
        current_hp=100,
        unit=make_unit_definition(unit_types)
    )

    process_move_effects(move, attacker, [target], current_turn=0, db=db)

    assert target.status_effects == []


def test_decrement_and_expire_status_effects(db, user):
    game = models.Game(
        game_name="Status Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="status-game"
    )
    db.add(game)
    db.flush()

    unit = models.GameUnit(
        game_id=game.id,
        unit_id=None,
        user_id=user.id,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=50,
        current_stats={"hp": 50},
        status_effects=["sleep", 1],
        is_fainted=False,
        move_pp=[]
    )
    db.add(unit)
    db.commit()

    modified = decrement_and_expire_status_effects(user.id, game.id, db)

    db.refresh(unit)
    assert unit.id in modified
    assert unit.status_effects == []


def test_process_move_effects_normalizes_badly_poisoned_name(db):
    move = models.Move(
        name="Toxic Test",
        type="poison",
        category="Status",
        effects=["target:status:badly_poison"]
    )
    attacker = models.GameUnit(status_effects=[])
    target = models.GameUnit(status_effects=[], current_hp=100)

    process_move_effects(move, attacker, [target], current_turn=0, db=db)

    assert len(target.status_effects) == 2
    assert target.status_effects[0] == "badly_poisoned"


def test_decrement_and_expire_status_effects_burn_deals_one_eighth_max_hp(db, user):
    game = models.Game(
        game_name="Burn Tick Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="burn-tick-game"
    )
    db.add(game)
    db.flush()

    unit = models.GameUnit(
        game_id=game.id,
        unit_id=None,
        user_id=user.id,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=80,
        current_stats={"hp": 80},
        status_effects=["burn", 4],
        is_fainted=False,
        move_pp=[]
    )
    db.add(unit)
    db.commit()

    decrement_and_expire_status_effects(user.id, game.id, db)
    db.refresh(unit)

    assert unit.current_hp == 70  # 1/8 of 80 = 10
    assert unit.status_effects == ["burn", 3]


def test_decrement_and_expire_status_effects_badly_poisoned_scales_damage(db, user):
    game = models.Game(
        game_name="Toxic Tick Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="toxic-tick-game"
    )
    db.add(game)
    db.flush()

    unit = models.GameUnit(
        game_id=game.id,
        unit_id=None,
        user_id=user.id,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=160,
        current_stats={"hp": 160},
        status_effects=["badly_poisoned", 4, 1],
        is_fainted=False,
        move_pp=[]
    )
    db.add(unit)
    db.commit()

    decrement_and_expire_status_effects(user.id, game.id, db)
    db.refresh(unit)
    assert unit.current_hp == 150  # 1/16 of 160 = 10
    assert unit.status_effects == ["badly_poisoned", 3, 2]

    decrement_and_expire_status_effects(user.id, game.id, db)
    db.refresh(unit)
    assert unit.current_hp == 130  # next turn 2/16 of 160 = 20
    assert unit.status_effects == ["badly_poisoned", 2, 3]


def test_decrement_and_expire_status_effects_paralysis_can_lock_action(db, user, monkeypatch):
    game = models.Game(
        game_name="Paralysis Tick Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="paralysis-tick-game"
    )
    db.add(game)
    db.flush()

    unit = models.GameUnit(
        game_id=game.id,
        unit_id=None,
        user_id=user.id,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=100,
        current_stats={"hp": 100},
        status_effects=["paralysis", 4],
        is_fainted=False,
        can_move=True,
        move_pp=[]
    )
    db.add(unit)
    db.commit()

    # Force paralysis proc
    monkeypatch.setattr("app.routes.games.random.randint", lambda _a, _b: 1)

    decrement_and_expire_status_effects(user.id, game.id, db)
    db.refresh(unit)

    assert unit.can_move is False
    assert unit.status_effects == ["paralysis", 3]


def test_decrement_and_expire_status_effects_sleep_always_locks_action(db, user):
    game = models.Game(
        game_name="Sleep Tick Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="sleep-tick-game"
    )
    db.add(game)
    db.flush()

    unit = models.GameUnit(
        game_id=game.id,
        unit_id=None,
        user_id=user.id,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=100,
        current_stats={"hp": 100},
        status_effects=["sleep", 4],
        is_fainted=False,
        can_move=True,
        move_pp=[]
    )
    db.add(unit)
    db.commit()

    decrement_and_expire_status_effects(user.id, game.id, db)
    db.refresh(unit)

    assert unit.can_move is False
    assert unit.status_effects == ["sleep", 3]


def test_decrement_and_expire_status_effects_cured_sleep_does_not_lock_action(db, user):
    game = models.Game(
        game_name="Sleep Cure Tick Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="sleep-cure-tick-game"
    )
    db.add(game)
    db.flush()

    unit = models.GameUnit(
        game_id=game.id,
        unit_id=None,
        user_id=user.id,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=100,
        current_stats={"hp": 100},
        status_effects=["sleep", 1],
        is_fainted=False,
        can_move=True,
        move_pp=[]
    )
    db.add(unit)
    db.commit()

    decrement_and_expire_status_effects(user.id, game.id, db)
    db.refresh(unit)

    assert unit.status_effects == []
    assert unit.can_move is True


def test_move_deals_direct_damage_for_special_with_power():
    move = models.Move(name="Flamethrower", category="Special", power=90)
    assert move_deals_direct_damage(move) is True


def test_move_deals_direct_damage_false_for_status_zero_power():
    move = models.Move(name="Toxic", category="Status", power=0)
    assert move_deals_direct_damage(move) is False


def test_apply_damage_based_move_effects_drain_uses_summed_damage(db):
    move = models.Move(
        name="Drain Test",
        category="Special",
        effects=["self:drain:2"],
    )
    attacker = models.GameUnit(current_hp=50, current_stats={"hp": 100})
    target1 = models.GameUnit(current_hp=70, current_stats={"hp": 100})
    target2 = models.GameUnit(current_hp=80, current_stats={"hp": 100})

    damage_results = [
        {"id": 1, "damage": 30, "current_hp": 70},
        {"id": 2, "damage": 20, "current_hp": 80},
    ]

    fainted_ids = apply_damage_based_move_effects(move, attacker, [target1, target2], damage_results, db)

    assert fainted_ids == []
    assert attacker.current_hp == 75  # floor((30 + 20) / 2) = 25 healed


def test_apply_damage_based_move_effects_recoil_uses_summed_damage(db):
    move = models.Move(
        name="Recoil Test",
        category="Physical",
        effects=["self:recoil:damage_dealt:4"],
    )
    attacker = models.GameUnit(id=10, current_hp=40, current_stats={"hp": 100})
    target1 = models.GameUnit(id=1, current_hp=60, current_stats={"hp": 100})
    target2 = models.GameUnit(id=2, current_hp=80, current_stats={"hp": 100})

    damage_results = [
        {"id": 1, "damage": 24, "current_hp": 60},
        {"id": 2, "damage": 16, "current_hp": 80},
    ]

    fainted_ids = apply_damage_based_move_effects(move, attacker, [target1, target2], damage_results, db)

    assert fainted_ids == []
    assert attacker.current_hp == 30  # floor((24 + 16) / 4) = 10 recoil


def test_apply_damage_based_move_effects_target_recoil_updates_targets_and_results(db):
    move = models.Move(
        name="Target Recoil Test",
        category="Special",
        effects=["target:recoil:damage_dealt:2"],
    )
    attacker = models.GameUnit(id=99, current_hp=100, current_stats={"hp": 100})
    target1 = models.GameUnit(id=1, current_hp=20, current_stats={"hp": 100})
    target2 = models.GameUnit(id=2, current_hp=50, current_stats={"hp": 100})

    damage_results = [
        {"id": 1, "damage": 18, "current_hp": 20},
        {"id": 2, "damage": 12, "current_hp": 50},
    ]

    fainted_ids = apply_damage_based_move_effects(move, attacker, [target1, target2], damage_results, db)

    # floor((18 + 12) / 2) = 15 recoil to each target recipient
    assert target1.current_hp == 5
    assert target2.current_hp == 35
    assert fainted_ids == []
    assert damage_results[0]["current_hp"] == 5
    assert damage_results[1]["current_hp"] == 35


def test_apply_damage_based_move_effects_recoil_maximum_hp_uses_recipient_max_hp(db):
    move = models.Move(
        name="Max HP Recoil Test",
        category="Physical",
        effects=["self:recoil:maximum_hp:4"],
    )
    attacker = models.GameUnit(id=10, current_hp=40, current_stats={"hp": 120})
    target = models.GameUnit(id=1, current_hp=70, current_stats={"hp": 100})

    # damage dealt should not affect maximum_hp recoil amount
    damage_results = [
        {"id": 1, "damage": 10, "current_hp": 70},
    ]

    fainted_ids = apply_damage_based_move_effects(move, attacker, [target], damage_results, db)

    # floor(120 / 4) = 30 recoil
    assert fainted_ids == []
    assert attacker.current_hp == 10


def test_move_deals_direct_damage_false_for_physical_zero_power():
    move = models.Move(name="NonDamaging", category="Physical", power=0)
    assert move_deals_direct_damage(move) is False


def test_movement_range_backend_enemy_tile_blocks_path():
    # 1x4 corridor, all movement costs are 1. Start at (0, 0).
    # With range 3 and enemy at (1, 0), tiles beyond are unreachable without passing through it.
    movement_costs = [
        [1, 1, 1, 1],
    ]

    tiles = movement_range_backend(
        start=(0, 0),
        rng=3,
        movement_costs=movement_costs,
        width=4,
        height=1,
        blocked_tiles={(1, 0)},
    )

    assert [1, 0] not in tiles
    assert [2, 0] not in tiles
    assert [3, 0] not in tiles


def test_movement_range_backend_allies_are_pass_through_when_not_blocked():
    movement_costs = [
        [1, 1, 1],
        [1, 1, 1],
        [1, 1, 1],
    ]

    tiles = movement_range_backend(
        start=(1, 1),
        rng=2,
        movement_costs=movement_costs,
        width=3,
        height=3,
        blocked_tiles=set(),
    )

    # This tile is reachable in 2 steps if no blocker is present.
    assert [2, 0] in tiles
