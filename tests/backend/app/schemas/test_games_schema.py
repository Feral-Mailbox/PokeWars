from app.schemas.games import GameCreateRequest, PlayerInfo, HostInfo, GameResponse, GameStateSchema
from app.schemas.maps import MapDetail
from datetime import datetime

def test_game_create_request():
    data = {
        "game_name": "Test Game",
        "map_name": "Arena",
        "max_players": 2,
        "is_private": True,
        "gamemode": "Conquest"
    }
    model = GameCreateRequest(**data)
    assert model.max_players == 2
    assert model.cash_per_turn is None

def test_player_info_fields():
    model = PlayerInfo(id=1, player_id=5, username="Ash", cash_remaining=100, is_ready=False)
    assert model.is_ready is False

def test_host_info_fields():
    model = HostInfo(id=99, username="HostGuy")
    assert model.username == "HostGuy"

def test_game_response_fields():
    map_data = MapDetail(id=1, name="Arena", allowed_modes=["Conquest"], allowed_player_counts=[2], width=10, height=10, tileset_names=["grass"], tile_data={})
    game = GameResponse(
        id=1,
        is_private=True,
        game_name="Battle",
        map_name="Arena",
        map=map_data,
        max_players=2,
        host_id=1,
        players=[],
        winner_id=None,
        gamemode="Conquest",
        status="open",
        current_turn=None,
        starting_cash=None,
        cash_per_turn=None,
        max_turns=None,
        unit_limit=None,
        replay_log=None,
        link="abc123",
        timestamp=datetime.now()
    )
    assert game.map.name == "Arena"

def test_game_state_schema():
    model = GameStateSchema(
        id=1, game_id=2, player_id=3, status="in_progress",
        game_units=[], cash_remaining=500
    )
    assert model.status == "in_progress"
