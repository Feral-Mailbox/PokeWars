"""Special move trait categories stored as a single integer on Move.move_trait.

Each move is at most one of these (or none). Overlaps that exist in mainline
(e.g. Air Cutter = wind + slicing) keep the primary trait here; combat helpers
may still use slug fallbacks for the secondary category where needed.
"""

from __future__ import annotations

from typing import Any

MOVE_TRAIT_NONE = 0
MOVE_TRAIT_SOUND = 1
MOVE_TRAIT_WIND = 2
MOVE_TRAIT_SLICING = 3
MOVE_TRAIT_BITING = 4
MOVE_TRAIT_PUNCHING = 5
MOVE_TRAIT_PULSE = 6
MOVE_TRAIT_POWDER = 7
MOVE_TRAIT_BALL_BOMB = 8

MOVE_TRAIT_BY_NAME: dict[str, int] = {
    "none": MOVE_TRAIT_NONE,
    "sound": MOVE_TRAIT_SOUND,
    "wind": MOVE_TRAIT_WIND,
    "slicing": MOVE_TRAIT_SLICING,
    "biting": MOVE_TRAIT_BITING,
    "bite": MOVE_TRAIT_BITING,
    "punching": MOVE_TRAIT_PUNCHING,
    "punch": MOVE_TRAIT_PUNCHING,
    "pulse": MOVE_TRAIT_PULSE,
    "powder": MOVE_TRAIT_POWDER,
    "ball_bomb": MOVE_TRAIT_BALL_BOMB,
    "ball": MOVE_TRAIT_BALL_BOMB,
    "bomb": MOVE_TRAIT_BALL_BOMB,
}

MOVE_TRAIT_NAME_BY_VALUE: dict[int, str] = {
    MOVE_TRAIT_NONE: "none",
    MOVE_TRAIT_SOUND: "sound",
    MOVE_TRAIT_WIND: "wind",
    MOVE_TRAIT_SLICING: "slicing",
    MOVE_TRAIT_BITING: "biting",
    MOVE_TRAIT_PUNCHING: "punching",
    MOVE_TRAIT_PULSE: "pulse",
    MOVE_TRAIT_POWDER: "powder",
    MOVE_TRAIT_BALL_BOMB: "ball_bomb",
}


def parse_move_trait(value: Any) -> int:
    """Normalize seed/API values to a move_trait int."""
    if value is None or value is False:
        return MOVE_TRAIT_NONE
    if isinstance(value, bool):
        return MOVE_TRAIT_NONE
    if isinstance(value, int):
        return value if value in MOVE_TRAIT_NAME_BY_VALUE else MOVE_TRAIT_NONE
    if isinstance(value, float) and value.is_integer():
        ivalue = int(value)
        return ivalue if ivalue in MOVE_TRAIT_NAME_BY_VALUE else MOVE_TRAIT_NONE
    if isinstance(value, str):
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        if key.isdigit():
            ivalue = int(key)
            return ivalue if ivalue in MOVE_TRAIT_NAME_BY_VALUE else MOVE_TRAIT_NONE
        return MOVE_TRAIT_BY_NAME.get(key, MOVE_TRAIT_NONE)
    return MOVE_TRAIT_NONE


def move_has_trait(move: Any, trait: int) -> bool:
    raw = getattr(move, "move_trait", None)
    if raw is None:
        return False
    try:
        return int(raw) == int(trait)
    except (TypeError, ValueError):
        return False
