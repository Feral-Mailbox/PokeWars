# tests/apps/backend/app/routes/test_games_route.py
import pytest
import app.db.models as models
from fastapi.testclient import TestClient

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
