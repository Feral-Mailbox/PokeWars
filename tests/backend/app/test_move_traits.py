from types import SimpleNamespace

from app.move_traits import (
    MOVE_TRAIT_BALL_BOMB,
    MOVE_TRAIT_BITING,
    MOVE_TRAIT_NONE,
    MOVE_TRAIT_POWDER,
    MOVE_TRAIT_PUNCHING,
    MOVE_TRAIT_SOUND,
    MOVE_TRAIT_WIND,
    move_has_trait,
    parse_move_trait,
)


def test_parse_move_trait_none_and_bool():
    assert parse_move_trait(None) == MOVE_TRAIT_NONE
    assert parse_move_trait(False) == MOVE_TRAIT_NONE
    assert parse_move_trait(True) == MOVE_TRAIT_NONE


def test_parse_move_trait_int_and_float():
    assert parse_move_trait(MOVE_TRAIT_SOUND) == MOVE_TRAIT_SOUND
    assert parse_move_trait(99) == MOVE_TRAIT_NONE
    assert parse_move_trait(3.0) == 3
    assert parse_move_trait(3.5) == MOVE_TRAIT_NONE
    assert parse_move_trait(99.0) == MOVE_TRAIT_NONE


def test_parse_move_trait_string_aliases():
    assert parse_move_trait("sound") == MOVE_TRAIT_SOUND
    assert parse_move_trait(" Wind ") == MOVE_TRAIT_WIND
    assert parse_move_trait("ball-bomb") == MOVE_TRAIT_BALL_BOMB
    assert parse_move_trait("bite") == MOVE_TRAIT_BITING
    assert parse_move_trait("punch") == MOVE_TRAIT_PUNCHING
    assert parse_move_trait("1") == MOVE_TRAIT_SOUND
    assert parse_move_trait("99") == MOVE_TRAIT_NONE
    assert parse_move_trait("unknown") == MOVE_TRAIT_NONE


def test_parse_move_trait_unsupported_type():
    assert parse_move_trait([1]) == MOVE_TRAIT_NONE
    assert parse_move_trait({"sound": 1}) == MOVE_TRAIT_NONE


def test_move_has_trait():
    move = SimpleNamespace(move_trait=MOVE_TRAIT_POWDER)
    assert move_has_trait(move, MOVE_TRAIT_POWDER) is True
    assert move_has_trait(move, MOVE_TRAIT_SOUND) is False
    assert move_has_trait(SimpleNamespace(), MOVE_TRAIT_SOUND) is False
    assert move_has_trait(SimpleNamespace(move_trait="nope"), MOVE_TRAIT_SOUND) is False
    assert move_has_trait(SimpleNamespace(move_trait=None), MOVE_TRAIT_SOUND) is False
