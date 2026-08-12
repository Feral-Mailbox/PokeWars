"""Tests for WS game_patch helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.game_patches import (
    build_game_patch_payload,
    next_event_seq,
    players_op,
    publish_game_patch,
    read_turnlock,
    turn_op_from_state,
    unit_to_patch,
)


def test_unit_to_patch_and_turn_op():
    unit = SimpleNamespace(
        id=7,
        game_id=1,
        unit_id=3,
        user_id=9,
        current_x=2,
        current_y=4,
        starting_x=1,
        starting_y=1,
        level=50,
        current_hp=12,
        current_stats={"attack": 10},
        stat_boosts={},
        status_effects=[],
        states=[],
        is_fainted=False,
        can_move=False,
        move_pp=[5, 5],
        held_item="Oran Berry",
        held_item_slug="oran-berry",
        held_tm_move_id=None,
        equipped_move_ids=[1],
        ability="Static",
        ability_id=2,
        unit=SimpleNamespace(
            id=3,
            name="Pikachu",
            types=["Electric"],
            base_stats={},
            sprite_url=None,
            asset_folder="025_pikachu",
            cost=100,
        ),
        flags={"jailed": True, "jailed_by": 2},
        jailed=True,
        jailed_by=2,
    )
    patch = unit_to_patch(unit)
    assert patch["id"] == 7
    assert patch["can_move"] is False
    assert patch["unit"]["name"] == "Pikachu"
    assert patch["unit"]["asset_folder"] == "025_pikachu"
    assert patch["unit"]["cost"] == 100
    assert patch["jailed"] is True
    assert patch["jailed_by"] == 2

    state = SimpleNamespace(
        current_turn=3,
        turn_deadline=None,
        status=SimpleNamespace(value="in_progress"),
        winner_id=None,
        players=[9, 8],
    )
    turn = turn_op_from_state(state)
    assert turn["op"] == "turn"
    assert turn["current_turn"] == 3
    assert turn["players"] == [9, 8]


def test_publish_game_patch_increments_seq_and_publishes_json():
    r = MagicMock()
    r.incr.return_value = 42
    seq = publish_game_patch(
        r,
        "abc",
        [{"op": "unit_removed", "unit_id": 1}],
        cause="unit_removed",
    )
    assert seq == 42
    r.incr.assert_called_once()
    args = r.publish.call_args[0]
    assert args[0] == "game_updates:abc"
    import json

    payload = json.loads(args[1])
    assert payload["event"] == "game_patch"
    assert payload["event_seq"] == 42
    assert payload["cause"] == "unit_removed"
    assert payload["ops"][0]["op"] == "unit_removed"


def test_publish_game_patch_skips_empty():
    r = MagicMock()
    assert publish_game_patch(r, "abc", []) == 0
    r.publish.assert_not_called()


def test_read_turnlock_and_players_op():
    r = MagicMock()
    r.hgetall.return_value = {"11": '{"origin":[1,2],"tiles":[[1,2],[1,3]]}'}
    locks = read_turnlock(r, "g", 5)
    assert locks["11"]["origin"] == [1, 2]

    rows = [
        SimpleNamespace(player_id=5, cash_remaining=100, is_ready=True, game_units=[1, 2]),
    ]
    assert players_op(rows)["players"][0]["cash_remaining"] == 100
    assert players_op([]) is None

    r.incr.return_value = 7
    assert next_event_seq(r, "g") == 7
    payload = build_game_patch_payload(event_seq=1, ops=[], cause="x", refetch=["player"])
    assert payload["refetch"] == ["player"]
