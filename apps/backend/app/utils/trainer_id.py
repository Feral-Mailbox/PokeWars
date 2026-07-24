"""Public trainer IDs: unique 32-bit values rendered as 8-char hex strings."""

from __future__ import annotations

import secrets

TRAINER_ID_BITS = 32
TRAINER_ID_HEX_LENGTH = TRAINER_ID_BITS // 4  # 8


def generate_trainer_id() -> str:
    """Return a random 32-bit trainer id as uppercase hex (e.g. ``A3F2C91B``)."""
    return f"{secrets.randbits(TRAINER_ID_BITS):0{TRAINER_ID_HEX_LENGTH}X}"


def allocate_unique_trainer_id(connection, table) -> str:
    """Pick a trainer_id that is not already present in ``users.trainer_id``."""
    from sqlalchemy import select

    for _ in range(64):
        candidate = generate_trainer_id()
        existing = connection.execute(
            select(table.c.id).where(table.c.trainer_id == candidate).limit(1)
        ).first()
        if existing is None:
            return candidate
    raise RuntimeError("Failed to allocate a unique trainer_id")
