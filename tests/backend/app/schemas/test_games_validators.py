import pytest
from pydantic import ValidationError

from app.schemas.games import GameCreateRequest


def test_game_create_request_default_turn_seconds():
    model = GameCreateRequest(
        game_name="G",
        map_name="M",
        max_players=2,
        is_private=False,
        gamemode="Conquest",
    )
    assert model.turn_seconds == 300


def test_game_create_request_turn_seconds_none_becomes_default():
    model = GameCreateRequest(
        game_name="G",
        map_name="M",
        max_players=2,
        is_private=False,
        gamemode="Conquest",
        turn_seconds=None,
    )
    assert model.turn_seconds == 300


def test_game_create_request_turn_seconds_bounds():
    with pytest.raises(ValidationError):
        GameCreateRequest(
            game_name="G",
            map_name="M",
            max_players=2,
            is_private=False,
            gamemode="Conquest",
            turn_seconds=10,
        )
    with pytest.raises(ValidationError):
        GameCreateRequest(
            game_name="G",
            map_name="M",
            max_players=2,
            is_private=False,
            gamemode="Conquest",
            turn_seconds=100_000,
        )

    ok = GameCreateRequest(
        game_name="G",
        map_name="M",
        max_players=2,
        is_private=False,
        gamemode="Conquest",
        turn_seconds=60,
    )
    assert ok.turn_seconds == 60
